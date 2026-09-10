"""pgvector semantic retrieval over chunk embeddings.

Cosine distance (`<=>`) via pgvector's SQLAlchemy comparator, matching
the HNSW index's `vector_cosine_ops` opclass defined on `Chunk` in
app/models.py (`idx_chunks_embedding_hnsw`) — the distance function used
in a query must match the index's opclass for the index to be usable.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Chunk, Document
from app.retrieval.filters import SearchFilters, apply_filters


@dataclass(frozen=True)
class VectorHit:
    chunk: Chunk
    distance: float


def vector_search(
    db: Session,
    query_embedding: list[float],
    *,
    limit: int,
    filters: SearchFilters | None = None,
) -> list[VectorHit]:
    distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")

    stmt = (
        select(Chunk, distance)
        .join(Document, Chunk.document_id == Document.id)
        .options(joinedload(Chunk.document))
        .where(Chunk.embedding.isnot(None))
        .order_by(distance.asc())
        .limit(limit)
    )
    stmt = apply_filters(stmt, filters)

    rows = db.execute(stmt).all()
    return [VectorHit(chunk=chunk, distance=float(dist)) for chunk, dist in rows]
