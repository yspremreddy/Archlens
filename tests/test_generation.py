import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.generation.groundedness import score_groundedness
from app.generation.prompts import SYSTEM_PROMPT, ContextItem, build_user_prompt
from app.generation.providers import (
    OLLAMA_PROVIDER_NAME,
    TEMPLATE_PROVIDER_NAME,
    UNKNOWN_ANSWER,
    LLMProviderError,
    LLMResult,
    OllamaProvider,
    TemplateExtractiveProvider,
)
from app.generation.schemas import AnswerRequest
from app.generation.service import answer_question
from app.models import Finding, FindingEvidence


# ---------------------------------------------------------------------------
# groundedness (pure unit tests, no DB)
# ---------------------------------------------------------------------------


def test_groundedness_full_overlap_scores_high():
    result = score_groundedness(
        "the payment service stores billing postal code",
        ["the payment service stores billing postal code for fraud scoring"],
        min_score=0.3,
    )
    assert result.score == pytest.approx(1.0)
    assert result.is_grounded
    assert not result.is_abstention


def test_groundedness_no_overlap_scores_low():
    result = score_groundedness(
        "elephants migrate across the savanna every winter",
        ["the payment service stores billing postal code for fraud scoring"],
        min_score=0.3,
    )
    assert result.score < 0.3
    assert not result.is_grounded


def test_groundedness_abstention_is_always_grounded():
    result = score_groundedness(UNKNOWN_ANSWER, [], min_score=0.3)
    assert result.score == 1.0
    assert result.is_grounded
    assert result.is_abstention


# ---------------------------------------------------------------------------
# TemplateExtractiveProvider (pure unit tests, no DB, no network)
# ---------------------------------------------------------------------------


def test_template_provider_quotes_top_context_item():
    prompt = build_user_prompt(
        "what stores postal codes?",
        [
            ContextItem(index=1, source="payment-service.md", chunk_index=0, text="payment-db stores postal codes."),
            ContextItem(index=2, source="other.md", chunk_index=1, text="unrelated text"),
        ],
    )
    result = TemplateExtractiveProvider().generate(system_prompt=SYSTEM_PROMPT, user_prompt=prompt)
    assert result.provider == TEMPLATE_PROVIDER_NAME
    assert "payment-db stores postal codes." in result.text
    assert "unrelated text" not in result.text


def test_template_provider_returns_unknown_with_no_context():
    prompt = build_user_prompt("anything?", [])
    result = TemplateExtractiveProvider().generate(system_prompt=SYSTEM_PROMPT, user_prompt=prompt)
    assert result.text == UNKNOWN_ANSWER


# ---------------------------------------------------------------------------
# OllamaProvider (mocked HTTP — no real network / local Ollama required)
# ---------------------------------------------------------------------------


def test_ollama_provider_parses_response(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return httpx.Response(
            200, json={"response": "  the answer  "}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr("app.generation.providers.httpx.post", fake_post)

    provider = OllamaProvider(host="http://localhost:11434", model="llama3.2:1b", timeout_seconds=5)
    result = provider.generate(system_prompt="sys", user_prompt="usr")

    assert result.text == "the answer"
    assert result.provider == OLLAMA_PROVIDER_NAME
    assert result.model == "llama3.2:1b"
    assert captured["url"] == "http://localhost:11434/api/generate"
    assert captured["json"]["system"] == "sys"
    assert captured["json"]["prompt"] == "usr"
    assert captured["json"]["stream"] is False


def test_ollama_provider_raises_on_connection_error(monkeypatch):
    def fake_post(url, json, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.generation.providers.httpx.post", fake_post)

    provider = OllamaProvider(host="http://localhost:11434", model="llama3.2:1b", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate(system_prompt="sys", user_prompt="usr")


def test_ollama_provider_raises_on_missing_response_field(monkeypatch):
    def fake_post(url, json, timeout):
        return httpx.Response(200, json={"unexpected": "shape"}, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.generation.providers.httpx.post", fake_post)

    provider = OllamaProvider(host="http://localhost:11434", model="llama3.2:1b", timeout_seconds=5)
    with pytest.raises(LLMProviderError):
        provider.generate(system_prompt="sys", user_prompt="usr")


# ---------------------------------------------------------------------------
# strict system/user separation
# ---------------------------------------------------------------------------


class _RecordingProvider:
    """Records exactly what it was called with, for asserting the pipeline
    never leaks retrieved content into the system prompt."""

    def __init__(self):
        self.calls = []

    def generate(self, *, system_prompt: str, user_prompt: str) -> LLMResult:
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt})
        return LLMResult(text=UNKNOWN_ANSWER, provider="recording", model="n/a")


def test_system_prompt_never_contains_retrieved_content(
    client: TestClient, ingested_samples: dict[str, str], db_session
):
    recorder = _RecordingProvider()
    request = AnswerRequest(question="what does payment-service store?", top_k=3, mode="hybrid")

    answer_question(db_session, request, provider=recorder)

    assert len(recorder.calls) == 1
    call = recorder.calls[0]
    assert call["system_prompt"] == SYSTEM_PROMPT
    assert "payment-db" not in call["system_prompt"]
    assert "postal code" not in call["system_prompt"]
    # the question and retrieved chunk text belong only in the user prompt
    assert "what does payment-service store?" in call["user_prompt"]


# ---------------------------------------------------------------------------
# end-to-end pipeline via the API (default template-extractive provider)
# ---------------------------------------------------------------------------


def test_answer_endpoint_grounded_response_persists_finding(
    client: TestClient, ingested_samples: dict[str, str], db_session
):
    resp = client.post(
        "/answer",
        json={"question": "what happens to billing postal codes?", "top_k": 3, "mode": "hybrid"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["answer"]
    assert body["llm_provider"] == TEMPLATE_PROVIDER_NAME
    assert body["retrieved_count"] > 0
    assert len(body["citations"]) == body["retrieved_count"]
    assert body["is_grounded"] is True
    assert body["groundedness_score"] == pytest.approx(1.0)
    assert body["finding_id"] is not None

    finding = db_session.get(Finding, uuid.UUID(body["finding_id"]))
    assert finding is not None
    assert finding.statement == body["answer"]
    assert finding.status == "open"

    evidence = (
        db_session.query(FindingEvidence).filter_by(finding_id=finding.id).all()
    )
    assert len(evidence) == body["retrieved_count"]


def test_answer_endpoint_abstains_with_no_documents(client: TestClient):
    resp = client.post("/answer", json={"question": "anything at all?", "top_k": 3, "mode": "hybrid"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"] == UNKNOWN_ANSWER
    assert body["is_abstention"] is True
    assert body["retrieved_count"] == 0
    assert body["citations"] == []


def test_answer_endpoint_respects_structured_filter(
    client: TestClient, ingested_samples: dict[str, str]
):
    payment_id = ingested_samples["payment-service.md"]
    resp = client.post(
        "/answer",
        json={
            "question": "what does this service do?",
            "top_k": 5,
            "mode": "hybrid",
            "filters": {"document_id": payment_id},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["retrieved_count"] > 0
    assert all(c["document_id"] == payment_id for c in body["citations"])


def test_answer_endpoint_rejects_empty_question(client: TestClient):
    resp = client.post("/answer", json={"question": "", "top_k": 3, "mode": "hybrid"})
    assert resp.status_code == 422
