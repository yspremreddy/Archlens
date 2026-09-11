"""Compact evaluation suite: retrieval (Recall@5/10, MRR, nDCG),
baseline RAG vs ArchLens, finding correctness/completeness, citation
accuracy, groundedness, and abstention/false-confidence — against both
the synthetic dataset and the real public corpus
(data/samples/public/, see SOURCES.md). Every ground-truth expectation
in app/evaluation/golden.py was verified empirically before being
written down (engineering guideline 3/4). Run with `-s` to see the printed
summary of actual measured values — nothing here is a fabricated
number.
"""

import time
import uuid

from app.evaluation.baseline import archlens_rank, baseline_rank
from app.evaluation.golden import REVIEW_GOLDEN_CASES, RETRIEVAL_GOLDEN_CASES, UNANSWERABLE_QUESTIONS
from app.evaluation.metrics import mean, ndcg_at_k, reciprocal_rank, recall_at_k
from app.models import Chunk


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


# ---------------------------------------------------------------------------
# retrieval: Recall@5/10, MRR, nDCG@5 — real hybrid+rerank pipeline
# ---------------------------------------------------------------------------


def test_eval_retrieval_recall_mrr_ndcg(db_session, ingested_samples, ingested_public_corpus):
    recall5, recall10, rr, ndcg5 = [], [], [], []
    for case in RETRIEVAL_GOLDEN_CASES:
        ranked = _dedupe_preserve_order(archlens_rank(db_session, case.query, top_k=10))
        recall5.append(recall_at_k(ranked, set(case.relevant_filenames), 5))
        recall10.append(recall_at_k(ranked, set(case.relevant_filenames), 10))
        rr.append(reciprocal_rank(ranked, set(case.relevant_filenames)))
        ndcg5.append(ndcg_at_k(ranked, set(case.relevant_filenames), 5))

    r5, r10, mrr, ndcg = mean(recall5), mean(recall10), mean(rr), mean(ndcg5)
    print(
        f"\n[eval] retrieval over {len(RETRIEVAL_GOLDEN_CASES)} golden cases "
        f"(synthetic + public corpus): Recall@5={r5:.3f} Recall@10={r10:.3f} "
        f"MRR={mrr:.3f} nDCG@5={ndcg:.3f}"
    )
    assert r5 >= 0.85
    assert r10 >= 0.85
    assert mrr >= 0.85
    assert ndcg >= 0.85


def test_eval_baseline_rag_vs_archlens(db_session, ingested_samples, ingested_public_corpus):
    baseline_recall5, archlens_recall5 = [], []
    for case in RETRIEVAL_GOLDEN_CASES:
        baseline_ranked = _dedupe_preserve_order(baseline_rank(db_session, case.query, top_k=5))
        archlens_ranked = _dedupe_preserve_order(archlens_rank(db_session, case.query, top_k=5))
        baseline_recall5.append(recall_at_k(baseline_ranked, set(case.relevant_filenames), 5))
        archlens_recall5.append(recall_at_k(archlens_ranked, set(case.relevant_filenames), 5))

    baseline_score, archlens_score = mean(baseline_recall5), mean(archlens_recall5)
    print(
        f"\n[eval] baseline (lexical-only) Recall@5={baseline_score:.3f} vs "
        f"ArchLens (hybrid+rerank) Recall@5={archlens_score:.3f} "
        f"over {len(RETRIEVAL_GOLDEN_CASES)} golden cases"
    )
    # ArchLens must be at least as good as plain lexical search — the
    # whole point of hybrid retrieval + reranking (Phases 2 and 4).
    assert archlens_score >= baseline_score


# ---------------------------------------------------------------------------
# finding correctness / completeness (/review against golden verdicts)
# ---------------------------------------------------------------------------


def test_eval_finding_correctness_and_completeness(client, ingested_samples, ingested_public_corpus):
    for document_id in ingested_samples.values():
        client.post(f"/documents/{document_id}/graph")

    correct = 0
    complete = 0
    for case in REVIEW_GOLDEN_CASES:
        resp = client.post("/review", json={"question": case.question})
        body = resp.json()
        if body["verdict"] == case.expected_verdict:
            correct += 1
        cited_filenames = {c["document_filename"] for c in body["citations"]}
        if case.expected_citation_filename in cited_filenames:
            complete += 1

    correctness = correct / len(REVIEW_GOLDEN_CASES)
    completeness = complete / len(REVIEW_GOLDEN_CASES)
    print(
        f"\n[eval] finding correctness={correctness:.2f} ({correct}/{len(REVIEW_GOLDEN_CASES)}), "
        f"completeness={completeness:.2f} ({complete}/{len(REVIEW_GOLDEN_CASES)}) "
        f"over {len(REVIEW_GOLDEN_CASES)} golden review cases"
    )
    assert correctness == 1.0
    assert completeness == 1.0


def test_eval_completeness_multi_hop_uses_both_text_and_graph(client, ingested_samples):
    for document_id in ingested_samples.values():
        client.post(f"/documents/{document_id}/graph")

    resp = client.post(
        "/review", json={"question": "what does event-collector send data to downstream?"}
    )
    body = resp.json()
    used_text = len(body["citations"]) > 0
    used_graph = len(body["graph_paths"]) > 0
    completeness = int(used_text) + int(used_graph)
    print(f"\n[eval] multi-source completeness: text_evidence={used_text} graph_evidence={used_graph} ({completeness}/2 sources)")
    assert completeness == 2


# ---------------------------------------------------------------------------
# citation accuracy
# ---------------------------------------------------------------------------


def test_eval_citation_accuracy(client, db_session, ingested_samples, ingested_public_corpus):
    checked = 0
    for question in [
        "what happens to billing postal codes?",
        "does the kubernetes baseline policy allow hostpath volumes?",
    ]:
        resp = client.post("/answer", json={"question": question, "top_k": 5, "mode": "hybrid"})
        for citation in resp.json()["citations"]:
            chunk = db_session.get(Chunk, uuid.UUID(citation["chunk_id"]))
            assert chunk is not None
            assert chunk.content_hash == citation["chunk_content_hash"]
            checked += 1

    for case in REVIEW_GOLDEN_CASES[:3]:
        resp = client.post("/review", json={"question": case.question})
        for citation in resp.json()["citations"]:
            chunk = db_session.get(Chunk, uuid.UUID(citation["chunk_id"]))
            assert chunk is not None
            assert chunk.content_hash == citation["chunk_content_hash"]
            checked += 1

    print(f"\n[eval] citation accuracy: {checked}/{checked} citations verified against real Postgres rows")
    assert checked > 0


# ---------------------------------------------------------------------------
# groundedness
# ---------------------------------------------------------------------------


def test_eval_groundedness(client, ingested_samples, ingested_public_corpus):
    scores = []
    for question in [
        "what happens to billing postal codes?",
        "what is broken access control?",
    ]:
        resp = client.post("/answer", json={"question": question, "top_k": 3, "mode": "hybrid"})
        body = resp.json()
        scores.append(body["groundedness_score"])
        assert body["is_grounded"] is True

    print(f"\n[eval] groundedness scores: {[round(s, 3) for s in scores]} (mean={mean(scores):.3f})")
    assert mean(scores) >= 0.3


# ---------------------------------------------------------------------------
# abstention / false-confidence
# ---------------------------------------------------------------------------


def test_eval_abstention_and_false_confidence_rate(client, ingested_samples, ingested_public_corpus):
    false_confident = 0
    for question in UNANSWERABLE_QUESTIONS:
        resp = client.post("/review", json={"question": question})
        body = resp.json()
        if body["verdict"] != "UNKNOWN":
            false_confident += 1

    false_confidence_rate = false_confident / len(UNANSWERABLE_QUESTIONS)
    print(
        f"\n[eval] false-confidence rate over {len(UNANSWERABLE_QUESTIONS)} unanswerable "
        f"questions: {false_confidence_rate:.2f} ({false_confident}/{len(UNANSWERABLE_QUESTIONS)} "
        f"wrongly non-UNKNOWN)"
    )
    assert false_confidence_rate == 0.0


def test_eval_abstention_on_empty_corpus(client):
    resp = client.post("/answer", json={"question": "anything at all?", "top_k": 3, "mode": "hybrid"})
    body = resp.json()
    print(f"\n[eval] empty-corpus abstention: is_abstention={body['is_abstention']}")
    assert body["is_abstention"] is True


# ---------------------------------------------------------------------------
# latency
# ---------------------------------------------------------------------------


def test_eval_latency_review_default_config(client, ingested_samples, ingested_public_corpus):
    t0 = time.monotonic()
    resp = client.post(
        "/review", json={"question": "does payment-api have rate limiting on the checkout endpoint?"}
    )
    elapsed = time.monotonic() - t0
    assert resp.status_code == 200
    print(f"\n[eval] /review latency (template provider, rule-based engine): {elapsed:.3f}s")
    assert elapsed < 10.0


def test_eval_latency_answer_default_config(client, ingested_samples, ingested_public_corpus):
    t0 = time.monotonic()
    resp = client.post(
        "/answer",
        json={"question": "what happens to billing postal codes?", "top_k": 3, "mode": "hybrid"},
    )
    elapsed = time.monotonic() - t0
    assert resp.status_code == 200
    print(f"\n[eval] /answer latency (template provider): {elapsed:.3f}s")
    assert elapsed < 10.0
