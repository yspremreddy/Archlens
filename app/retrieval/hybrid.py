"""Hybrid fusion of lexical and vector retrieval via Reciprocal Rank Fusion.

RRF (Cormack et al., 2009) combines two ranked lists purely by rank
position, not by the two methods' raw scores — which is exactly why it's
the right fusion method here: `ts_rank_cd` (lexical) and cosine distance
(vector) are not on comparable scales, so mixing them by raw score would
silently let whichever method happens to produce bigger numbers dominate.
RRF score for a chunk = sum over each list it appears in of 1/(k + rank),
with the standard k=60 constant (from the original paper; not tuned
against ArchLens data — revisit if/when there's a golden eval set to tune
against, per docs/ROADMAP.md's evaluation phase).
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.ingestion.embedding import embed_text
from app.models import Chunk
from app.retrieval.filters import SearchFilters
from app.retrieval.lexical import lexical_search
from app.retrieval.vector import vector_search

DEFAULT_RRF_K = 60
CANDIDATE_POOL_MULTIPLIER = 5
MIN_CANDIDATE_POOL = 20


@dataclass(frozen=True)
class HybridHit:
    chunk: Chunk
    rrf_score: float
    lexical_rank: int | None
    vector_rank: int | None


def reciprocal_rank_fusion(
    lexical_hits: list, vector_hits: list, *, k: int = DEFAULT_RRF_K
) -> list[HybridHit]:
    scores: dict[UUID, float] = {}
    chunks_by_id: dict[UUID, Chunk] = {}
    lexical_ranks: dict[UUID, int] = {}
    vector_ranks: dict[UUID, int] = {}

    for rank, hit in enumerate(lexical_hits, start=1):
        cid = hit.chunk.id
        chunks_by_id[cid] = hit.chunk
        lexical_ranks[cid] = rank
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)

    for rank, hit in enumerate(vector_hits, start=1):
        cid = hit.chunk.id
        chunks_by_id[cid] = hit.chunk
        vector_ranks[cid] = rank
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)

    ordered_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
    return [
        HybridHit(
            chunk=chunks_by_id[cid],
            rrf_score=scores[cid],
            lexical_rank=lexical_ranks.get(cid),
            vector_rank=vector_ranks.get(cid),
        )
        for cid in ordered_ids
    ]


def hybrid_search(
    db: Session,
    query: str,
    *,
    limit: int,
    filters: SearchFilters | None = None,
    k: int = DEFAULT_RRF_K,
) -> list[HybridHit]:
    candidate_pool = max(limit * CANDIDATE_POOL_MULTIPLIER, MIN_CANDIDATE_POOL)

    lexical_hits = lexical_search(db, query, limit=candidate_pool, filters=filters)

    query_embedding = embed_text(query)
    vector_hits = vector_search(db, query_embedding, limit=candidate_pool, filters=filters)

    fused = reciprocal_rank_fusion(lexical_hits, vector_hits, k=k)
    return fused[:limit]
