"""PostgreSQL full-text (lexical) retrieval over chunk text.

Uses `plainto_tsquery` (handles arbitrary user text safely — no tsquery
syntax injection) against a functional `to_tsvector('english', text)`
expression, matching the GIN index defined on `Chunk` in app/models.py
(`idx_chunks_text_fts`). Ranked with `ts_rank_cd`, Postgres's
cover-density ranking (rewards matched terms appearing close together),
which is a reasonable default for short architecture-doc chunks.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Chunk, Document
from app.retrieval.filters import SearchFilters, apply_filters


@dataclass(frozen=True)
class LexicalHit:
    chunk: Chunk
    rank: float


def lexical_search(
    db: Session, query: str, *, limit: int, filters: SearchFilters | None = None
) -> list[LexicalHit]:
    query = query.strip()
    if not query:
        return []

    tsvector = func.to_tsvector("english", Chunk.text)
    tsquery = func.plainto_tsquery("english", query)
    rank = func.ts_rank_cd(tsvector, tsquery).label("rank")

    stmt = (
        select(Chunk, rank)
        .join(Document, Chunk.document_id == Document.id)
        .options(joinedload(Chunk.document))
        .where(tsvector.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(limit)
    )
    stmt = apply_filters(stmt, filters)

    rows = db.execute(stmt).all()
    return [LexicalHit(chunk=chunk, rank=float(rank_value)) for chunk, rank_value in rows]
