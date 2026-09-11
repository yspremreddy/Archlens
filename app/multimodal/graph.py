"""Component/relationship extraction from a diagram, feeding the same
Postgres `components` table and Neo4j graph that text-document
extraction does (app/graph/service.py) — reuses its upsert helpers
directly rather than a parallel implementation.

Two distinct signals, combined conservatively:
- **Component names**: OCR text regions (app/multimodal/ocr.py) that
  look like a label — a short slug, not prose. OCR is deterministic and
  reliable; there is no "vision understanding" risk here, just text
  recognition.
- **Relationships**: parsed from the vision model's caption
  (app/multimodal/vision.py), which is asked (by prompt) to list
  connections as `SourceName -> TargetName` lines. This *is* a real
  vision-model claim (an OCR pass cannot see an arrow), so each parsed
  relationship is only kept if BOTH endpoint names were independently
  confirmed by OCR — a vision-model hallucination naming a component
  that isn't actually in the diagram is filtered out rather than
  trusted (CLAUDE.md rule 3: don't fabricate/pass through unverified
  claims as fact).

Postgres `components.extraction_method = 'vision_extracted'`
distinguishes this path from text-document extraction's `'rule_based'`
(migration `cc8e51c1a598`) — component *names* here come from OCR, but
the pipeline as a whole (OCR + vision) is the diagram-ingestion path,
so it is labeled distinctly from prose extraction rather than reusing
either 'rule_based' or 'llm_extracted', neither of which accurately
describes it.
"""

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.graph.schema import REL_SENDS_DATA_TO, ensure_graph_schema
from app.graph.service import (
    GraphExtractionResult,
    find_evidence_chunk,
    upsert_graph_component,
    upsert_graph_relationship,
    upsert_postgres_component,
)
from app.models import Chunk, Document

_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$")
_ARROW_LINE_RE = re.compile(r"^\s*([A-Za-z][\w\- ]*?)\s*(?:->|→)\s*([A-Za-z][\w\- ]*?)\s*$")

_TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("datastore", ("-db", "database", "cache", "warehouse", "store")),
    ("queue", ("-queue", "-bus", "queue", "topic")),
    ("service", ("-api", "-service", "-worker", "-collector", "-gateway")),
)


def _looks_like_component_label(text: str) -> bool:
    return bool(_SLUG_RE.match(text.strip()))


def _infer_type_from_name(name: str) -> str:
    lower = name.lower()
    for type_, keywords in _TYPE_KEYWORDS:
        if any(k in lower for k in keywords):
            return type_
    return "other"


@dataclass(frozen=True)
class VisionRelationship:
    source_name: str
    target_name: str


def parse_vision_relationships(
    caption_text: str, known_names: list[str]
) -> list[VisionRelationship]:
    name_by_lower = {n.lower(): n for n in known_names}
    relationships = []
    for line in caption_text.splitlines():
        m = _ARROW_LINE_RE.match(line)
        if not m:
            continue
        source = name_by_lower.get(m.group(1).strip().lower())
        target = name_by_lower.get(m.group(2).strip().lower())
        if source and target and source != target:
            relationships.append(VisionRelationship(source, target))
    return relationships


def extract_graph_for_visual_document(db: Session, document: Document) -> GraphExtractionResult:
    """Reads component candidates from this document's OCR chunks and
    relationships from its vision-caption chunk (both already persisted
    by app/multimodal/service.py at ingestion time — this does not
    re-run OCR/vision, it only parses what was already extracted)."""
    from sqlalchemy import select

    ensure_graph_schema()

    chunks = list(
        db.execute(
            select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.chunk_index)
        )
        .scalars()
        .all()
    )

    ocr_chunks = [c for c in chunks if c.modality == "image_ocr"]
    caption_chunks = [c for c in chunks if c.modality == "image_caption"]

    candidate_names = {c.text.strip() for c in ocr_chunks if _looks_like_component_label(c.text)}

    pg_components: dict[str, object] = {}
    for name in sorted(candidate_names):
        evidence_chunk = find_evidence_chunk(chunks, name)
        pg_row = upsert_postgres_component(
            db,
            document=document,
            name=name,
            type_=_infer_type_from_name(name),
            description=f"Component labeled '{name}' in an architecture diagram.",
            owner=None,
            evidence_chunk=evidence_chunk,
            extraction_method="vision_extracted",
        )
        pg_components[name] = pg_row
        upsert_graph_component(
            pg_component_id=pg_row.id,
            name=name,
            type_=pg_row.type,
            document_id=document.id,
            chunk_id=pg_row.source_chunk_id,
        )

    relationships: list[VisionRelationship] = []
    for caption_chunk in caption_chunks:
        relationships.extend(
            parse_vision_relationships(caption_chunk.text, list(candidate_names))
        )

    for rel in relationships:
        source = pg_components.get(rel.source_name)
        target = pg_components.get(rel.target_name)
        if source is None or target is None:
            continue
        evidence_chunk = caption_chunks[0] if caption_chunks else None
        upsert_graph_relationship(
            kind=REL_SENDS_DATA_TO,
            source_pg_id=source.id,
            target_pg_id=target.id,
            document_id=document.id,
            chunk_id=evidence_chunk.id if evidence_chunk else None,
        )

    db.commit()

    return GraphExtractionResult(
        document_id=str(document.id),
        components_upserted=len(pg_components),
        relationships_upserted=len(relationships),
        owner_linked=False,
    )
