"""Graph retrieval for multi-hop dependency/data-flow questions.

Traverses SENDS_DATA_TO/DEPENDS_ON edges up to a bounded number of hops
(callers must pass an explicit max_hops; app.config.Settings.graph_max_hops
is the app-wide default/cap) — no unbounded traversal, consistent with
docs/ARCHITECTURE.md's "bounded reasoning" principle even though this
isn't the agentic-reasoning bound specifically.

Every hop's evidence is resolved back to a full Citation
(app.retrieval.schemas.Citation — the same shape /search and /answer
use) via the pg_document_id/pg_chunk_id properties stored on the Neo4j
relationship (app/graph/service.py) — "integrate graph results with the
existing retrieval/evidence model."
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph.client import get_graph_session
from app.graph.schema import COMPONENT_LABEL, REL_DEPENDS_ON, REL_SENDS_DATA_TO
from app.models import Chunk, Document
from app.retrieval.schemas import Citation

_TRAVERSABLE_RELS = f"{REL_SENDS_DATA_TO}|{REL_DEPENDS_ON}"
_VALID_DIRECTIONS = ("downstream", "upstream", "both")


@dataclass(frozen=True)
class GraphHop:
    source_name: str
    target_name: str
    relationship_type: str
    citation: Citation | None


@dataclass(frozen=True)
class GraphPath:
    component_names: list[str]  # start .. end, in traversal order
    hops: list[GraphHop]


def _citation_from_pg_ids(
    db: Session, document_id: str | None, chunk_id: str | None
) -> Citation | None:
    if not document_id or not chunk_id:
        return None
    row = db.execute(
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.id == UUID(chunk_id), Document.id == UUID(document_id))
    ).first()
    if row is None:
        return None
    chunk, document = row
    return Citation(
        document_id=document.id,
        document_filename=document.original_filename,
        document_content_hash=document.content_hash,
        chunk_id=chunk.id,
        chunk_index=chunk.chunk_index,
        chunk_content_hash=chunk.content_hash,
        start_offset=chunk.start_offset,
        end_offset=chunk.end_offset,
    )


def _pattern(direction: str, max_hops: int) -> str:
    rel = f"[rels:{_TRAVERSABLE_RELS}*1..{max_hops}]"
    if direction == "downstream":
        return f"(start:{COMPONENT_LABEL} {{name: $name}})-{rel}->(end:{COMPONENT_LABEL})"
    if direction == "upstream":
        return f"(start:{COMPONENT_LABEL} {{name: $name}})<-{rel}-(end:{COMPONENT_LABEL})"
    return f"(start:{COMPONENT_LABEL} {{name: $name}})-{rel}-(end:{COMPONENT_LABEL})"


def find_paths(
    db: Session,
    component_name: str,
    *,
    direction: str = "downstream",
    max_hops: int = 3,
) -> list[GraphPath]:
    if direction not in _VALID_DIRECTIONS:
        raise ValueError(f"invalid direction: {direction!r}, expected one of {_VALID_DIRECTIONS}")
    max_hops = max(1, max_hops)

    query = f"""
    MATCH path = {_pattern(direction, max_hops)}
    RETURN [n IN nodes(path) | n.name] AS names,
           [r IN relationships(path) | {{
               type: type(r), source: startNode(r).name, target: endNode(r).name,
               pg_document_id: r.pg_document_id, pg_chunk_id: r.pg_chunk_id
           }}] AS rels
    """

    with get_graph_session() as session:
        records = list(session.run(query, name=component_name))

    paths: list[GraphPath] = []
    for record in records:
        hops = [
            GraphHop(
                source_name=r["source"],
                target_name=r["target"],
                relationship_type=r["type"],
                citation=_citation_from_pg_ids(db, r["pg_document_id"], r["pg_chunk_id"]),
            )
            for r in record["rels"]
        ]
        paths.append(GraphPath(component_names=record["names"], hops=hops))
    return paths


def component_exists(component_name: str) -> bool:
    with get_graph_session() as session:
        result = session.run(
            f"MATCH (c:{COMPONENT_LABEL} {{name: $name}}) RETURN c LIMIT 1", name=component_name
        )
        return result.single() is not None
