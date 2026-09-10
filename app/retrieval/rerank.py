"""Phase 4: local cross-encoder reranking.

A modular, optional step applied after retrieval and before generation:
takes the top-N candidates from whatever retrieval already produced
(hybrid by default) and reorders them by a cross-encoder's relevance
score. A cross-encoder scores the (query, passage) pair jointly, which is
a materially better relevance signal than lexical rank or vector distance
alone — but it's too slow to run over an entire retrieved set or corpus,
which is why it only ever sees the top N candidates, never everything
retrieval returned.

Uses fastembed's `TextCrossEncoder` (ONNX runtime) — the same local,
open-source, no-API-key, no-torch approach already used for embeddings
(app/ingestion/embedding.py) and consistent with docs/DECISIONS.md's
preference for ONNX-based local models. Model:
`Xenova/ms-marco-MiniLM-L-6-v2` (~80MB, MS MARCO-trained, Apache-2.0).

This module does not know about hybrid/lexical/vector retrieval, the
generation pipeline, or /search — it operates purely on
`RetrievedResult` objects (app/retrieval/core.py), which already carry
each result's `Chunk` (and therefore full citation/provenance) alongside
whatever score/rank retrieval produced. Reranking only ever replaces
`.score` and reorders the list; the `Chunk`, and therefore every
citation field derived from it (document id, chunk id, both content
hashes, offsets — see app.retrieval.core.citation_for), is untouched.
This keeps reranking a drop-in step that any caller (currently just the
generation pipeline) can opt into without changing retrieval itself,
per "keep the existing retrieval architecture."
"""

import dataclasses
from functools import lru_cache

from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.config import get_settings
from app.retrieval.core import RetrievedResult


@lru_cache
def _get_reranker() -> TextCrossEncoder:
    return TextCrossEncoder(model_name=get_settings().rerank_model_name)


def rerank_results(
    query: str, results: list[RetrievedResult], *, top_n: int
) -> list[RetrievedResult]:
    """Reranks only `results[:top_n]` (the top-N candidates from whatever
    retrieval already ran) by cross-encoder relevance. Anything beyond
    `top_n` is left untouched, appended after the reranked head in its
    original order — so callers can safely pass a larger candidate list
    than they intend to rerank without losing the tail.

    An empty or single-element `results` is returned as-is (nothing
    meaningful to reorder).
    """
    if len(results) <= 1 or top_n <= 0:
        return results

    head, tail = results[:top_n], results[top_n:]
    passages = [r.chunk.text for r in head]
    scores = list(_get_reranker().rerank(query, passages))

    reranked_head = [
        dataclasses.replace(result, score=float(score))
        for result, score in sorted(
            zip(head, scores, strict=True), key=lambda pair: pair[1], reverse=True
        )
    ]
    return reranked_head + tail
