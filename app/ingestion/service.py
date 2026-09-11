"""Ingestion foundation: upload -> store -> chunk -> embed -> persist.

This is deliberately synchronous and minimal for Phase 1 (no background
worker/queue) — a document is fully ingested within the request that
uploads it. Untrusted input handling (CLAUDE.md rule 6): the uploaded
bytes are treated as opaque data throughout — decoded as text for
chunking, never executed, never interpolated into a path (the on-disk
filename is the content hash, not the client-supplied name).
"""

import hashlib
import uuid
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.ingestion.chunking import chunk_text
from app.ingestion.embedding import embed_texts
from app.models import AuditLog, Chunk, Document


def sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def store_raw_bytes(content: bytes, content_hash: str) -> str:
    settings = get_settings()
    storage_dir = Path(settings.storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    # Filename derived from the hash, never from the untrusted client
    # filename, so it can never be used for path traversal.
    safe_name = content_hash.replace(":", "_")
    dest = storage_dir / safe_name
    if not dest.exists():
        dest.write_bytes(content)
    return str(dest)


def ingest_document(
    db: Session,
    *,
    filename: str,
    content: bytes,
    mime_type: str | None,
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
    db.flush()  # assign document.id

    db.add(
        AuditLog(
            event_type="document.uploaded",
            entity_type="document",
            entity_id=document.id,
            detail={"filename": filename, "size_bytes": len(content)},
        )
    )

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        document.status = "failed"
        document.error_message = f"could not decode as UTF-8 text: {exc}"
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

    spans = chunk_text(text)
    if spans:
        vectors = embed_texts([s.text for s in spans])
        for span, vector in zip(spans, vectors, strict=True):
            db.add(
                Chunk(
                    document_id=document.id,
                    chunk_index=span.index,
                    text=span.text,
                    start_offset=span.start_offset,
                    end_offset=span.end_offset,
                    token_count=span.token_count,
                    content_hash=sha256_hex(span.text.encode("utf-8")),
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
            detail={"chunk_count": len(spans)},
        )
    )
    db.commit()
    db.refresh(document)
    return document
