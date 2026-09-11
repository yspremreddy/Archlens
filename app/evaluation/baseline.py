"""Baseline RAG vs. ArchLens retrieval, for the evaluation suite's
"baseline RAG vs ArchLens" comparison.

**Baseline**: lexical-only (keyword/full-text) retrieval —
`app.retrieval.core.retrieve(mode="lexical")` — representing the
simplest RAG retrieval approach (keyword search alone, no vector
similarity, no reranking).

**ArchLens**: the actual production retrieval path — hybrid (lexical +
vector, Reciprocal Rank Fusion) retrieval followed by cross-encoder
reranking, exactly what `app/generation/service.py` uses for `/answer`
and what the agent's `search_tool` (app/agent/tools.py) uses for
`/review`. Not a separate reimplementation — the same two functions
production code calls.
"""

from sqlalchemy.orm import Session

from app.config import get_settings
from app.retrieval.core import retrieve
from app.retrieval.rerank import rerank_results


def baseline_rank(db: Session, query: str, *, top_k: int) -> list[str]:
    """Lexical-only retrieval — the baseline. Returns document filenames
    in ranked order (may contain duplicates if multiple chunks from the
    same document rank highly; callers wanting unique docs should
    dedupe)."""
    results = retrieve(db, query, top_k=top_k, mode="lexical")
    return [r.chunk.document.original_filename for r in results]


def archlens_rank(db: Session, query: str, *, top_k: int) -> list[str]:
    """Hybrid retrieval + cross-encoder reranking — what ArchLens
    actually uses in production (app/generation/service.py,
    app/agent/tools.py)."""
    settings = get_settings()
    candidate_k = max(top_k, settings.rerank_candidate_pool) if settings.rerank_enabled else top_k
    results = retrieve(db, query, top_k=candidate_k, mode="hybrid")
    if settings.rerank_enabled and results:
        results = rerank_results(query, results, top_n=settings.rerank_candidate_pool)
    results = results[:top_k]
    return [r.chunk.document.original_filename for r in results]
