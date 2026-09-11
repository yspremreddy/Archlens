"""Orchestrates extraction -> Postgres `components` upsert -> Neo4j
node/edge creation, keeping both sides linked by provenance.

Provenance model (engineering guideline 7, "preserve evidence/provenance"):
- Every Postgres `components` row already carries `source_document_id`/
  `source_chunk_id` (docs/SCHEMA.md §3) — this is where extraction
  populates them, for the first time (Phase 1 shipped the columns with
  nothing writing to them).
- Every Neo4j `:Component` node carries `pg_component_id` (its mirrored
  Postgres row's id) plus `pg_document_id`/`pg_chunk_id` — so a graph
  node's provenance is readable directly off the node, without a join,
  while `pg_component_id` remains the authoritative cross-reference.
- Every Neo4j relationship (`SENDS_DATA_TO`, `DEPENDS_ON`, `OWNED_BY`)
  carries `pg_document_id`/`pg_chunk_id` for the chunk the relationship
  claim was extracted from. Relationships have no Postgres mirror table
  (out of scope for this milestone — see docs/DECISIONS.md ADR-007);
  their provenance lives entirely as properties on the Neo4j edge itself.

Idempotent: re-running extraction for the same document updates existing
Postgres component rows (matched by source_document_id + name) and
MERGEs (not creates duplicate) Neo4j nodes/edges, so ingesting the same
sample data twice does not duplicate the graph.
"""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph.client import get_graph_session
from app.graph.extraction import ExtractionResult, extract
from app.graph.schema import (
    COMPONENT_LABEL,
    OWNER_LABEL,
    REL_OWNED_BY,
    ensure_graph_schema,
)
from app.models import Chunk, Component, Document


@dataclass(frozen=True)
class GraphExtractionResult:
    document_id: str
    components_upserted: int
    relationships_upserted: int
    owner_linked: bool


def find_evidence_chunk(chunks: list[Chunk], *needles: str) -> Chunk | None:
    """The first chunk whose text contains all of `needles` — a decent
    proxy for "the chunk this fact was actually extracted from", since
    the extractor only ever matches text that's literally present in the
    document (see app/graph/extraction.py)."""
    for chunk in chunks:
        if all(needle in chunk.text for needle in needles):
            return chunk
    return None


def upsert_postgres_component(
    db: Session,
    *,
    document: Document,
    name: str,
    type_: str,
    description: str,
    owner: str | None,
    evidence_chunk: Chunk | None,
    extraction_method: str = "rule_based",
) -> Component:
    """Shared by app/graph/service.py (text extraction) and
    app/multimodal/graph.py (diagram/vision extraction) — both write the
    same Postgres `components` rows, distinguished only by
    `extraction_method`."""
    existing = db.execute(
        select(Component).where(
            Component.source_document_id == document.id, Component.name == name
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = Component(
            name=name,
            type=type_,
            description=description,
            owner=owner,
            source_document_id=document.id,
            source_chunk_id=evidence_chunk.id if evidence_chunk else None,
            extraction_method=extraction_method,
        )
        db.add(existing)
    else:
        existing.type = type_
        existing.description = description
        if owner is not None:
            existing.owner = owner
        if evidence_chunk is not None:
            existing.source_chunk_id = evidence_chunk.id
        existing.extraction_method = extraction_method

    db.flush()  # assign/confirm id
    return existing


def upsert_graph_component(
    *, pg_component_id, name: str, type_: str, document_id, chunk_id
) -> None:
    with get_graph_session() as session:
        session.run(
            f"""
            MERGE (c:{COMPONENT_LABEL} {{pg_component_id: $pg_component_id}})
            SET c.name = $name,
                c.type = $type,
                c.pg_document_id = $document_id,
                c.pg_chunk_id = $chunk_id
            """,
            pg_component_id=str(pg_component_id),
            name=name,
            type=type_,
            document_id=str(document_id),
            chunk_id=str(chunk_id) if chunk_id else None,
        )


def upsert_graph_relationship(
    *, kind: str, source_pg_id, target_pg_id, document_id, chunk_id
) -> None:
    with get_graph_session() as session:
        session.run(
            f"""
            MATCH (a:{COMPONENT_LABEL} {{pg_component_id: $source_id}})
            MATCH (b:{COMPONENT_LABEL} {{pg_component_id: $target_id}})
            MERGE (a)-[r:{kind}]->(b)
            SET r.pg_document_id = $document_id,
                r.pg_chunk_id = $chunk_id
            """,
            source_id=str(source_pg_id),
            target_id=str(target_pg_id),
            document_id=str(document_id),
            chunk_id=str(chunk_id) if chunk_id else None,
        )


def _upsert_graph_owner(*, owner_name: str, component_pg_id, document_id, chunk_id) -> None:
    with get_graph_session() as session:
        session.run(
            f"""
            MERGE (o:{OWNER_LABEL} {{name: $owner_name}})
            WITH o
            MATCH (c:{COMPONENT_LABEL} {{pg_component_id: $component_id}})
            MERGE (c)-[r:{REL_OWNED_BY}]->(o)
            SET r.pg_document_id = $document_id,
                r.pg_chunk_id = $chunk_id
            """,
            owner_name=owner_name,
            component_id=str(component_pg_id),
            document_id=str(document_id),
            chunk_id=str(chunk_id) if chunk_id else None,
        )


def extract_graph_for_document(db: Session, document: Document) -> GraphExtractionResult:
    ensure_graph_schema()

    raw_text = Path(document.storage_path).read_text(encoding="utf-8")
    result: ExtractionResult = extract(raw_text)

    chunks = list(
        db.execute(
            select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.chunk_index)
        )
        .scalars()
        .all()
    )

    pg_components: dict[str, Component] = {}
    for comp in result.components:
        owner = (
            result.owner_team
            if (comp.name == result.primary_component_name and result.owner_team)
            else None
        )
        evidence_chunk = find_evidence_chunk(chunks, comp.description[:40])
        pg_row = upsert_postgres_component(
            db,
            document=document,
            name=comp.name,
            type_=comp.type,
            description=comp.description,
            owner=owner,
            evidence_chunk=evidence_chunk,
            extraction_method="rule_based",
        )
        pg_components[comp.name] = pg_row
        upsert_graph_component(
            pg_component_id=pg_row.id,
            name=comp.name,
            type_=comp.type,
            document_id=document.id,
            chunk_id=pg_row.source_chunk_id,
        )

    for rel in result.relationships:
        source = pg_components.get(rel.source_name)
        target = pg_components.get(rel.target_name)
        if source is None or target is None:
            continue
        evidence_chunk = find_evidence_chunk(chunks, rel.source_name, rel.target_name)
        upsert_graph_relationship(
            kind=rel.kind,
            source_pg_id=source.id,
            target_pg_id=target.id,
            document_id=document.id,
            chunk_id=evidence_chunk.id if evidence_chunk else None,
        )

    owner_linked = False
    if result.owner_team and result.primary_component_name in pg_components:
        primary = pg_components[result.primary_component_name]
        evidence_chunk = find_evidence_chunk(chunks, "Owned by the", result.owner_team)
        _upsert_graph_owner(
            owner_name=result.owner_team,
            component_pg_id=primary.id,
            document_id=document.id,
            chunk_id=evidence_chunk.id if evidence_chunk else None,
        )
        owner_linked = True

    db.commit()

    return GraphExtractionResult(
        document_id=str(document.id),
        components_upserted=len(pg_components),
        relationships_upserted=len(result.relationships),
        owner_linked=owner_linked,
    )
