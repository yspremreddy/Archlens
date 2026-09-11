"""Phase 6 (multimodal retrieval) tests: image/PDF ingestion, OCR,
vision captioning (mocked — no live model dependency by default,
matching the OllamaProvider test pattern in tests/test_generation.py),
visual evidence provenance, retrieval integration, and diagram-based
graph extraction.

Real end-to-end behavior (OCR against the actual diagram fixtures, and a
real Ollama `moondream` vision call) was verified manually during
development — see docs/DECISIONS.md ADR-008 for what that verification
found, including the vision model's real limitations. This suite uses
the default `VISION_PROVIDER=none` (NoOp) for determinism, plus one
narrowly-scoped live check gated on Ollama actually being reachable.
"""

import uuid
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.graph.client import get_graph_session
from app.models import Chunk, Component
from app.multimodal.graph import (
    VisionRelationship,
    _infer_type_from_name,
    _looks_like_component_label,
    parse_vision_relationships,
)
from app.multimodal.ocr import extract_regions
from app.multimodal.pdf import render_pdf_pages
from app.multimodal.vision import (
    OLLAMA_VISION_PROVIDER_NAME,
    OllamaVisionProvider,
    VisionProviderError,
)

DIAGRAMS_DIR = Path(__file__).resolve().parents[1] / "data" / "samples" / "diagrams"


@pytest.fixture(autouse=True)
def _clean_graph():
    with get_graph_session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    yield


# ---------------------------------------------------------------------------
# OCR and PDF rendering (pure, against the real fixture files)
# ---------------------------------------------------------------------------


def test_ocr_reads_the_real_diagram_labels():
    image = Image.open(DIAGRAMS_DIR / "payment-architecture.png")
    regions = extract_regions(image)
    texts = {r.text for r in regions}
    assert {"payment-api", "payment-db", "settlement-queue", "ledger-service"} <= texts
    for r in regions:
        assert r.confidence > 0.5
        assert r.bbox["x1"] > r.bbox["x0"]
        assert r.bbox["y1"] > r.bbox["y0"]


def test_pdf_renders_to_one_page_image():
    pdf_bytes = (DIAGRAMS_DIR / "payment-architecture.pdf").read_bytes()
    pages = render_pdf_pages(pdf_bytes)
    assert len(pages) == 1
    assert pages[0].size[0] > 0 and pages[0].size[1] > 0


# ---------------------------------------------------------------------------
# vision-caption relationship parsing (pure unit tests)
# ---------------------------------------------------------------------------


def test_parse_vision_relationships_accepts_known_names():
    caption = "This diagram shows a flow.\npayment-api -> settlement-queue\nsettlement-queue -> ledger-service\n"
    known = ["payment-api", "settlement-queue", "ledger-service", "payment-db"]
    rels = parse_vision_relationships(caption, known)
    assert VisionRelationship("payment-api", "settlement-queue") in rels
    assert VisionRelationship("settlement-queue", "ledger-service") in rels
    assert len(rels) == 2


def test_parse_vision_relationships_rejects_hallucinated_names():
    # "Larger-service" is not among the OCR-confirmed names — this is
    # the real degenerate output observed from the small vision model
    # during development (see docs/DECISIONS.md ADR-008); it must be
    # filtered out, not trusted.
    caption = "payment-api -> Larger-service\nLarger-service -> Larger-service\n"
    known = ["payment-api", "settlement-queue", "ledger-service", "payment-db"]
    rels = parse_vision_relationships(caption, known)
    assert rels == []


def test_component_label_heuristic():
    assert _looks_like_component_label("payment-api")
    assert _looks_like_component_label("analytics-warehouse")
    assert not _looks_like_component_label("Payment Service - Component Diagram")
    assert not _looks_like_component_label("hello")


def test_infer_type_from_name():
    assert _infer_type_from_name("payment-db") == "datastore"
    assert _infer_type_from_name("settlement-queue") == "queue"
    assert _infer_type_from_name("payment-api") == "service"
    assert _infer_type_from_name("ledger-service") == "service"


# ---------------------------------------------------------------------------
# OllamaVisionProvider (mocked HTTP — no real network/model dependency)
# ---------------------------------------------------------------------------


def test_ollama_vision_provider_parses_response(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["json"] = json
        return httpx.Response(
            200, json={"response": "  a diagram of things  "}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr("app.multimodal.vision.httpx.post", fake_post)
    provider = OllamaVisionProvider(host="http://localhost:11434", model="moondream", timeout_seconds=5)
    result = provider.describe(b"fake-image-bytes", prompt="describe this")

    assert result.caption == "a diagram of things"
    assert result.provider == OLLAMA_VISION_PROVIDER_NAME
    assert result.model == "moondream"
    assert captured["json"]["prompt"] == "describe this"
    assert isinstance(captured["json"]["images"], list) and len(captured["json"]["images"]) == 1


def test_ollama_vision_provider_raises_on_connection_error(monkeypatch):
    def fake_post(url, json, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.multimodal.vision.httpx.post", fake_post)
    provider = OllamaVisionProvider(host="http://localhost:11434", model="moondream", timeout_seconds=5)
    with pytest.raises(VisionProviderError):
        provider.describe(b"fake-image-bytes", prompt="describe this")


# ---------------------------------------------------------------------------
# ingestion: images and PDFs, with default (NoOp) vision provider
# ---------------------------------------------------------------------------


def _upload_diagram(client: TestClient, filename: str, content_type: str) -> dict:
    content = (DIAGRAMS_DIR / filename).read_bytes()
    resp = client.post("/documents", files={"file": (filename, content, content_type)})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_image_ingestion_creates_ocr_chunks_with_bbox_provenance(
    client: TestClient, db_session
):
    body = _upload_diagram(client, "payment-architecture.png", "image/png")
    assert body["status"] == "ingested"

    chunks = (
        db_session.query(Chunk)
        .filter_by(document_id=uuid.UUID(body["id"]))
        .order_by(Chunk.chunk_index)
        .all()
    )
    assert len(chunks) == 5  # title + 4 component labels, no vision provider by default
    for chunk in chunks:
        assert chunk.modality == "image_ocr"
        assert chunk.page_number == 1
        assert chunk.bbox is not None
        assert chunk.embedding is not None
        assert len(chunk.embedding) == 384
        assert chunk.content_hash.startswith("sha256:")

    texts = {c.text for c in chunks}
    assert "payment-api" in texts
    assert "settlement-queue" in texts


def test_pdf_ingestion_creates_ocr_chunks_matching_the_image_version(
    client: TestClient, db_session
):
    body = _upload_diagram(client, "payment-architecture.pdf", "application/pdf")
    assert body["status"] == "ingested"

    chunks = (
        db_session.query(Chunk).filter_by(document_id=uuid.UUID(body["id"])).all()
    )
    assert len(chunks) == 5
    assert all(c.modality == "image_ocr" and c.page_number == 1 for c in chunks)
    assert {c.text for c in chunks} == {
        "Payment Service - Component Diagram",
        "payment-api",
        "settlement-queue",
        "ledger-service",
        "payment-db",
    }


def test_no_caption_chunk_with_default_noop_vision_provider(client: TestClient, db_session):
    body = _upload_diagram(client, "payment-architecture.png", "image/png")
    chunks = db_session.query(Chunk).filter_by(document_id=uuid.UUID(body["id"])).all()
    assert all(c.modality != "image_caption" for c in chunks)


def test_corrupt_image_bytes_fails_gracefully(client: TestClient):
    resp = client.post(
        "/documents", files={"file": ("broken.png", b"not a real png", "image/png")}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["error_message"]


def test_unsupported_visual_suffix_rejected(client: TestClient):
    resp = client.post(
        "/documents", files={"file": ("diagram.gif", b"whatever", "image/gif")}
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# retrieval integration — same hybrid/lexical/vector search, no new code
# ---------------------------------------------------------------------------


def test_diagram_content_is_hybrid_searchable(client: TestClient):
    _upload_diagram(client, "payment-architecture.png", "image/png")

    resp = client.post(
        "/search", json={"query": "settlement-queue", "top_k": 5, "mode": "hybrid"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["result_count"] > 0
    top = body["results"][0]
    assert top["citation"]["modality"] == "image_ocr"
    assert top["citation"]["bbox"] is not None
    assert top["citation"]["page_number"] == 1


def test_modality_filter_restricts_to_diagram_chunks(
    client: TestClient, ingested_samples: dict[str, str]
):
    # ingested_samples ingests the text sample docs (fixture from
    # conftest.py) — combined with a diagram upload, this proves the
    # modality filter actually distinguishes them, not just that only
    # one modality happens to exist.
    _upload_diagram(client, "payment-architecture.png", "image/png")

    resp = client.post(
        "/search",
        json={
            "query": "payment",
            "top_k": 10,
            "mode": "hybrid",
            "filters": {"modality": "image_ocr"},
        },
    )
    body = resp.json()
    assert body["result_count"] > 0
    assert all(r["citation"]["modality"] == "image_ocr" for r in body["results"])


def test_answer_can_be_grounded_in_diagram_evidence(client: TestClient):
    _upload_diagram(client, "payment-architecture.png", "image/png")

    resp = client.post(
        "/answer",
        json={"question": "what is the settlement-queue?", "top_k": 3, "mode": "hybrid"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["retrieved_count"] > 0
    assert any(c["modality"] == "image_ocr" for c in body["citations"])


# ---------------------------------------------------------------------------
# graph extraction from a diagram
# ---------------------------------------------------------------------------


def test_graph_extraction_from_diagram_creates_components(client: TestClient, db_session):
    body = _upload_diagram(client, "payment-architecture.png", "image/png")
    resp = client.post(f"/documents/{body['id']}/graph")
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["components_upserted"] == 4  # not the title line

    components = (
        db_session.query(Component).filter_by(source_document_id=uuid.UUID(body["id"])).all()
    )
    assert len(components) == 4
    by_name = {c.name: c for c in components}
    assert by_name["payment-db"].type == "datastore"
    assert by_name["settlement-queue"].type == "queue"
    for c in components:
        assert c.extraction_method == "vision_extracted"
        assert c.source_chunk_id is not None

    with get_graph_session() as session:
        node_count = session.run(
            "MATCH (c:Component) WHERE c.pg_document_id = $doc_id RETURN count(c) AS n",
            doc_id=body["id"],
        ).single()["n"]
    assert node_count == 4


def test_graph_extraction_relationships_are_zero_without_vision_provider(
    client: TestClient,
):
    # Honest behavior, not a bug: with the default NoOp vision provider,
    # there is no caption to parse relationships from — zero
    # relationships is the correct, non-fabricated outcome.
    body = _upload_diagram(client, "payment-architecture.png", "image/png")
    resp = client.post(f"/documents/{body['id']}/graph")
    assert resp.json()["relationships_upserted"] == 0


# ---------------------------------------------------------------------------
# existing text/RAG/GraphRAG behavior unaffected
# ---------------------------------------------------------------------------


def test_text_ingestion_and_answer_unaffected_by_multimodal_changes(
    client: TestClient, ingested_samples: dict[str, str]
):
    resp = client.post(
        "/answer",
        json={
            "question": "what happens to billing postal codes?",
            "top_k": 3,
            "mode": "hybrid",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["retrieved_count"] > 0
    assert all(c["modality"] == "text" for c in body["citations"])
