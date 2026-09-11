"""Multimodal ingestion: image/PDF-page -> OCR text + optional vision
caption -> embeddings -> Postgres `chunks`, using the exact same
chunk/embedding/retrieval machinery as text ingestion
(app/ingestion/service.py). A chunk derived from OCR or a vision caption
is embedded with the same model (app/ingestion/embedding.py) and stored
in the same `chunks` table — only `modality`/`bbox`/`page_number`
distinguish it — so it is retrieved by the existing hybrid/lexical/
vector search (app/retrieval/) and eligible as `/answer` evidence with
*zero* changes to retrieval or generation code. See docs/DECISIONS.md
ADR-008 for why this integration path was chosen over a parallel
image-embedding system.

Untrusted input handling (CLAUDE.md rule 6): uploaded image/PDF bytes
are only ever passed to OCR/rendering/vision libraries as opaque pixel
data — never executed, never interpolated into a path (storage filename
is the content hash, matching app/ingestion/service.py).
"""

import io

from PIL import Image
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ingestion.embedding import embed_texts
from app.ingestion.service import sha256_hex, store_raw_bytes
from app.models import AuditLog, Chunk, Document
from app.multimodal.ocr import extract_regions
from app.multimodal.pdf import render_pdf_pages
from app.multimodal.vision import VisionProviderError, get_vision_provider

# Calibrated empirically against `moondream` (see docs/DECISIONS.md
# ADR-008): a compound instruction asking for a description *and* a
# strict "A -> B" relationship list in one call reliably produced
# degenerate repetition-loop output on this small model. This simpler,
# single-ask phrasing produces coherent, on-topic captions instead. The
# tradeoff, stated plainly: relationship extraction
# (app/multimodal/graph.py's `parse_vision_relationships`) will often
# find zero matches against this free-form prose, since it only accepts
# a strict "A -> B" line format — an honest limitation of this model,
# not silently hidden. Component names read via OCR remain reliable
# regardless, since OCR is text recognition, not free-form generation.
VISION_PROMPT = (
    "Describe this software architecture diagram: what components are "
    "shown, and how are they connected (e.g. 'payment-api connects to "
    "payment-db')."
)

PDF_MIME_TYPES = {"application/pdf"}
IMAGE_MIME_TYPES = {"image/png", "image/jpeg"}


def _is_pdf(filename: str, mime_type: str | None) -> bool:
    return mime_type in PDF_MIME_TYPES or filename.lower().endswith(".pdf")


def _ocr_records(image: Image.Image, *, page_number: int, next_index: int) -> list[dict]:
    records = []
    for i, region in enumerate(extract_regions(image)):
        records.append(
            {
                "chunk_index": next_index + i,
                "text": region.text,
                "modality": "image_ocr",
                "page_number": page_number,
                "bbox": region.bbox,
            }
        )
    return records


def _caption_record(image: Image.Image, *, page_number: int, chunk_index: int) -> dict | None:
    provider = get_vision_provider()
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    try:
        result = provider.describe(buf.getvalue(), prompt=VISION_PROMPT)
    except VisionProviderError:
        return None
    if result is None or not result.caption.strip():
        return None
    width, height = image.size
    return {
        "chunk_index": chunk_index,
        "text": result.caption,
        "modality": "image_caption",
        "page_number": page_number,
        "bbox": {"x0": 0, "y0": 0, "x1": width, "y1": height},
    }


def ingest_visual_document(
    db: Session, *, filename: str, content: bytes, mime_type: str | None
) -> Document:
    content_hash = sha256_hex(content)
    storage_path = store_raw_bytes(content, content_hash)

    document = Document(
        source_type="upload",
        original_filename=filename,
        mime_type=mime_type,
        file_size_bytes=len(content),
        storage_path=storage_path,
        content_hash=content_hash,
        status="pending",
    )
    db.add(document)
    db.flush()
    db.add(
        AuditLog(
            event_type="document.uploaded",
            entity_type="document",
            entity_id=document.id,
            detail={"filename": filename, "size_bytes": len(content), "kind": "visual"},
        )
    )

    try:
        if _is_pdf(filename, mime_type):
            images = render_pdf_pages(content)
        else:
            images = [Image.open(io.BytesIO(content)).convert("RGB")]
    except Exception as exc:
        document.status = "failed"
        document.error_message = f"could not render image/PDF: {exc}"
        db.add(
            AuditLog(
                event_type="document.ingestion_failed",
                entity_type="document",
                entity_id=document.id,
                detail={"reason": document.error_message},
            )
        )
        db.commit()
        db.refresh(document)
        return document

    records: list[dict] = []
    for page_number, image in enumerate(images, start=1):
        records.extend(_ocr_records(image, page_number=page_number, next_index=len(records)))
        caption = _caption_record(image, page_number=page_number, chunk_index=len(records))
        if caption is not None:
            records.append(caption)

    if records:
        vectors = embed_texts([r["text"] for r in records])
        for record, vector in zip(records, vectors, strict=True):
            db.add(
                Chunk(
                    document_id=document.id,
                    chunk_index=record["chunk_index"],
                    text=record["text"],
                    page_number=record["page_number"],
                    modality=record["modality"],
                    bbox=record["bbox"],
                    content_hash=sha256_hex(record["text"].encode("utf-8")),
                    embedding=vector,
                )
            )

    document.status = "ingested"
    document.ingested_at = func.now()
    db.add(
        AuditLog(
            event_type="document.ingested",
            entity_type="document",
            entity_id=document.id,
            detail={
                "chunk_count": len(records),
                "page_count": len(images),
                "ocr_chunk_count": sum(1 for r in records if r["modality"] == "image_ocr"),
                "caption_chunk_count": sum(
                    1 for r in records if r["modality"] == "image_caption"
                ),
            },
        )
    )
    db.commit()
    db.refresh(document)
    return document
