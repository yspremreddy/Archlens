"""Phase 4 reranking tests.

Two layers: pure unit tests of rerank_results() against hand-built
RetrievedResult objects (no DB, no model download beyond the reranker
itself), and an evaluation-style test that compares real hybrid
retrieval results before vs after reranking against the existing
synthetic dataset — verified empirically (see the scratch probe used
during development) rather than assumed: for the query "schema
validation for incoming events", hybrid retrieval ranks the
data-pipeline.md intro chunk (chunk 0) above the chunk that actually
discusses the schema-validation gap (chunk 1); reranking corrects this.
"""

import uuid
from dataclasses import dataclass

import pytest

from app.retrieval.core import RetrievedResult, citation_for, retrieve
from app.retrieval.rerank import rerank_results


@dataclass
class _FakeDocument:
    original_filename: str
    content_hash: str = "sha256:fake"


@dataclass
class _FakeChunk:
    id: uuid.UUID
    text: str
    document: _FakeDocument
    document_id: uuid.UUID
    chunk_index: int = 0
    content_hash: str = "sha256:fake"
    start_offset: int | None = None
    end_offset: int | None = None


def _fake_result(text: str, *, filename: str = "doc.md", score: float = 0.5) -> RetrievedResult:
    doc_id = uuid.uuid4()
    chunk = _FakeChunk(
        id=uuid.uuid4(), text=text, document=_FakeDocument(filename), document_id=doc_id
    )
    return RetrievedResult(
        chunk=chunk, score=score, lexical_rank=1, vector_rank=1, retrieval_methods=["hybrid"]
    )


# ---------------------------------------------------------------------------
# unit tests: rerank_results() in isolation
# ---------------------------------------------------------------------------


def test_rerank_promotes_the_more_relevant_passage():
    results = [
        _fake_result("The weather today is sunny with a light breeze."),
        _fake_result("payment-db stores billing postal code for fraud-scoring for 90 days."),
        _fake_result("auth-db stores hashed passwords using bcrypt."),
    ]
    reranked = rerank_results("how long is billing postal code retained?", results, top_n=10)

    assert "billing postal code" in reranked[0].chunk.text
    # scores strictly descending
    assert [r.score for r in reranked] == sorted([r.score for r in reranked], reverse=True)


def test_rerank_preserves_citation_provenance():
    results = [_fake_result(f"passage number {i}") for i in range(4)]
    before_ids = {r.chunk.id for r in results}

    reranked = rerank_results("passage number 2", results, top_n=10)
    after_ids = {r.chunk.id for r in reranked}

    assert before_ids == after_ids
    # every chunk object is untouched (same id, same text, same document) —
    # only score and position may have changed.
    reranked_by_id = {r.chunk.id: r for r in reranked}
    for original in results:
        assert reranked_by_id[original.chunk.id].chunk.text == original.chunk.text
        assert reranked_by_id[original.chunk.id].chunk.document.original_filename == (
            original.chunk.document.original_filename
        )


def test_rerank_only_touches_top_n_leaves_tail_untouched():
    results = [_fake_result(f"passage {i}", score=float(-i)) for i in range(5)]
    reranked = rerank_results("passage", results, top_n=2)

    # tail (index 2 onward) preserved in original order with original scores
    assert [r.chunk.id for r in reranked[2:]] == [r.chunk.id for r in results[2:]]
    assert [r.score for r in reranked[2:]] == [r.score for r in results[2:]]


def test_rerank_empty_results_is_noop():
    assert rerank_results("anything", [], top_n=10) == []


def test_rerank_single_result_is_noop():
    results = [_fake_result("only one passage")]
    assert rerank_results("query", results, top_n=10) == results


def test_rerank_top_n_zero_is_noop():
    results = [_fake_result("a"), _fake_result("b")]
    assert rerank_results("query", results, top_n=0) == results


# ---------------------------------------------------------------------------
# evaluation: real hybrid retrieval, before vs after, against the
# synthetic dataset
# ---------------------------------------------------------------------------


def test_reranking_corrects_a_real_hybrid_misranking(db_session, ingested_samples):
    query = "schema validation for incoming events"

    before = retrieve(db_session, query, top_k=6, mode="hybrid")
    after = rerank_results(query, before, top_n=6)

    # provenance: same set of chunks, nothing added/dropped/substituted
    assert {r.chunk.id for r in before} == {r.chunk.id for r in after}
    assert {citation_for(r.chunk).chunk_content_hash for r in before} == {
        citation_for(r.chunk).chunk_content_hash for r in after
    }

    # the passage that actually discusses the schema-validation gap
    target = next(
        r for r in before if "schema validation" in r.chunk.text and r.chunk.chunk_index == 1
    )
    before_rank = next(i for i, r in enumerate(before, 1) if r.chunk.id == target.chunk.id)
    after_rank = next(i for i, r in enumerate(after, 1) if r.chunk.id == target.chunk.id)

    assert before_rank > 1, "test assumption violated: hybrid should NOT already rank this #1"
    assert after_rank == 1, "reranking should promote the genuinely relevant passage to #1"


def test_reranking_never_regresses_an_already_correct_top_result(
    db_session, ingested_samples
):
    # For a query hybrid already gets right, reranking should not make
    # things worse — the correct top-1 should stay top-1.
    query = "rate limiting on the checkout endpoint"
    before = retrieve(db_session, query, top_k=6, mode="hybrid")
    after = rerank_results(query, before, top_n=6)

    assert before[0].chunk.document.original_filename == "payment-service.md"
    assert after[0].chunk.document.original_filename == "payment-service.md"
    assert after[0].chunk.id == before[0].chunk.id


def test_reranked_scores_replace_hybrid_rrf_scores(db_session, ingested_samples):
    query = "kafka message queue"
    before = retrieve(db_session, query, top_k=4, mode="hybrid")
    after = rerank_results(query, before, top_n=4)

    # RRF scores are small positive floats (sum of 1/(k+rank) terms);
    # cross-encoder logit scores can be negative and are on a different
    # scale entirely — confirms rerank_results actually replaced them,
    # not just reordered the original scores.
    assert all(0 < r.score < 1 for r in before)
    assert any(r.score < 0 for r in after) or max(r.score for r in after) > 1
