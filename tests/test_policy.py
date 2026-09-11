"""Phase 7 Architecture Review / Policy Engine tests.

Covers the marker-based verdict engine (app/policy/engine.py) directly —
including the false-positive bugs found and fixed during development
(cross-document contamination, the ambiguous "documented" keyword, and
generic-word false relevance matches) — and the end-to-end `POST
/review` pipeline against the real synthetic dataset.
"""

import uuid

from app.policy.engine import evaluate
from app.policy.markers import scan_text
from app.models import Finding


# ---------------------------------------------------------------------------
# marker scanning (pure unit tests)
# ---------------------------------------------------------------------------


def test_scan_detects_negation_without_false_affirmation():
    text = "payment-api currently has no documented rate limiting on the checkout endpoint."
    neg, pos = scan_text(text)
    assert neg is True
    assert pos is False  # regression test: bare "documented" used to false-match here


def test_scan_detects_affirmation_without_false_negation_on_never():
    text = "Password hashes use bcrypt with a per-user salt; raw passwords are never persisted or logged."
    neg, pos = scan_text(text)
    assert pos is True
    assert neg is False  # regression test: "never" used to false-match as a negation


# ---------------------------------------------------------------------------
# verdict engine (pure unit tests)
# ---------------------------------------------------------------------------


def test_evaluate_no_evidence_is_unknown():
    v = evaluate("does X have Y?", [])
    assert v.verdict == "UNKNOWN"
    assert v.confidence == 1.0


def test_evaluate_irrelevant_evidence_is_unknown():
    v = evaluate(
        "does the system support biometric login?",
        ["payment-db stores transaction amount, currency, and customer id."],
    )
    assert v.verdict == "UNKNOWN"


def test_evaluate_relevant_negation_is_fail():
    v = evaluate(
        "does payment-api have rate limiting on the checkout endpoint?",
        ["payment-api currently has no documented rate limiting on the checkout endpoint."],
    )
    assert v.verdict == "FAIL"
    assert v.severity in ("medium", "high")
    assert v.confidence > 0.5


def test_evaluate_relevant_affirmation_is_pass():
    v = evaluate(
        "are user passwords hashed with bcrypt?",
        ["Password hashes use bcrypt with a per-user salt for all user passwords."],
    )
    assert v.verdict == "PASS"
    assert v.confidence > 0.5


def test_evaluate_conflicting_evidence_is_conflict():
    v = evaluate(
        "is the payment database encrypted at rest?",
        [
            "The payment database is encrypted at rest using provider-managed keys.",
            "The payment database has no documented encryption at rest configuration.",
        ],
    )
    assert v.verdict == "CONFLICT"
    assert len(v.affirming_texts) == 1
    assert len(v.denying_texts) == 1


def test_evaluate_unrelated_document_negation_does_not_contaminate_verdict():
    # Regression test for the cross-document contamination bug found
    # during development: an unrelated document's "Known gaps" negation
    # must not leak into a verdict about a completely different topic
    # just because both were retrieved in the same top-k batch.
    v = evaluate(
        "are user passwords hashed with bcrypt?",
        [
            "Password hashes use bcrypt with a per-user salt for all user passwords.",
            "event-collector accepts events from any authenticated client without schema validation.",
        ],
    )
    assert v.verdict == "PASS"


def test_evaluate_unrelated_bullet_in_same_chunk_does_not_contaminate_verdict():
    # Regression test for ADR-010: a single retrieved chunk containing
    # three unrelated bullets used to make the whole chunk's negations/
    # affirmations count toward any question that matched *any* bullet's
    # keywords. Sentence-level scanning (_logical_units) must isolate
    # just the relevant bullet.
    chunk = (
        "- There is no documented mechanism for honoring a user deletion request "
        "against analytics-warehouse, deletion is currently a manual, "
        "case-by-case SQL operation.\n"
        "- event-collector accepts events from any authenticated client without "
        "schema validation, so malformed fields can reach event-bus unfiltered.\n"
        "- No component in this pipeline has an assigned data-protection owner."
    )
    v = evaluate("what does event-collector send data to downstream?", [chunk])
    assert v.verdict == "FAIL"
    assert len(v.denying_texts) == 1
    assert "event-collector" in v.denying_texts[0]
    assert "deletion request" not in v.denying_texts[0]
    assert "data-protection owner" not in v.denying_texts[0]


# ---------------------------------------------------------------------------
# /review end-to-end
# ---------------------------------------------------------------------------


def _extract_graph_for_all(client, ingested_samples):
    for document_id in ingested_samples.values():
        resp = client.post(f"/documents/{document_id}/graph")
        assert resp.status_code == 200, resp.text


def test_review_fail_case(client, db_session, ingested_samples):
    resp = client.post(
        "/review",
        json={"question": "does payment-api have rate limiting on the checkout endpoint?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verdict"] == "FAIL"
    assert body["severity"] in ("medium", "high")
    assert len(body["citations"]) > 0

    finding = db_session.get(Finding, uuid.UUID(body["finding_id"]))
    assert finding is not None
    assert finding.verdict == "FAIL"
    assert finding.severity == body["severity"]
    assert float(finding.confidence) == body["confidence"]


def test_review_pass_case(client, db_session, ingested_samples):
    resp = client.post("/review", json={"question": "are user passwords hashed with bcrypt?"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verdict"] == "PASS"
    assert len(body["citations"]) > 0


def test_review_unknown_case_for_unrelated_question(client, ingested_samples):
    resp = client.post(
        "/review", json={"question": "does the system support biometric login?"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verdict"] == "UNKNOWN"


def test_review_unknown_with_empty_corpus(client):
    resp = client.post("/review", json={"question": "anything at all?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "UNKNOWN"
    assert body["citations"] == []


def test_review_integrates_graph_evidence(client, db_session, ingested_samples):
    _extract_graph_for_all(client, ingested_samples)
    resp = client.post(
        "/review", json={"question": "what does event-collector send data to downstream?"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Regression test for the chunk-granularity contamination bug fixed
    # in ADR-010: this question's evidence chunk contains three unrelated
    # bullets (a deletion-mechanism gap, the schema-validation gap, and
    # an ownership gap); sentence-level scanning now correctly isolates
    # only the schema-validation bullet as relevant, giving a precise
    # FAIL rather than the CONFLICT this used to produce.
    assert body["verdict"] == "FAIL"
    assert "schema validation" in body["recommendation"]
    assert len(body["graph_paths"]) > 0
    assert len(body["citations"]) > 0
    assert body["agent_steps"] >= 2


def test_review_citations_match_real_postgres_evidence(client, db_session, ingested_samples):
    from app.models import Chunk

    resp = client.post(
        "/review", json={"question": "are user passwords hashed with bcrypt?"}
    )
    body = resp.json()
    assert body["citations"]
    for citation in body["citations"]:
        chunk = db_session.get(Chunk, uuid.UUID(citation["chunk_id"]))
        assert chunk is not None
        assert chunk.content_hash == citation["chunk_content_hash"]


def test_review_structured_filter_restricts_evidence_to_one_document(
    client, ingested_samples
):
    payment_id = ingested_samples["payment-service.md"]
    resp = client.post(
        "/review",
        json={
            "question": "does payment-api have rate limiting on the checkout endpoint?",
            "filters": {"document_id": payment_id},
        },
    )
    body = resp.json()
    assert body["citations"]
    assert all(c["document_id"] == payment_id for c in body["citations"])


def test_review_rejects_empty_question(client):
    resp = client.post("/review", json={"question": ""})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# backward compatibility: /answer is untouched by this phase
# ---------------------------------------------------------------------------


def test_answer_endpoint_still_works_unchanged(client, ingested_samples):
    resp = client.post(
        "/answer",
        json={"question": "what happens to billing postal codes?", "top_k": 3, "mode": "hybrid"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["retrieved_count"] > 0
    assert "verdict" not in body  # AnswerResponse schema is unchanged
