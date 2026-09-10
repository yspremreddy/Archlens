import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Chunk, Document

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"


def test_ingest_sample_document_creates_chunks_with_embeddings_and_provenance(db_session):
    client = TestClient(app)
    sample_path = SAMPLES_DIR / "payment-service.md"
    content = sample_path.read_bytes()

    resp = client.post(
        "/documents",
        files={"file": (sample_path.name, content, "text/markdown")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ingested"
    assert body["content_hash"].startswith("sha256:")

    document = db_session.get(Document, uuid.UUID(body["id"]))
    assert document is not None
    assert document.status == "ingested"
    assert document.ingested_at is not None
    assert document.storage_path  # raw bytes were persisted somewhere

    chunks = (
        db_session.execute(
            select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.chunk_index)
        )
        .scalars()
        .all()
    )
    assert len(chunks) > 0
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i
        assert chunk.text.strip() != ""
        assert chunk.content_hash.startswith("sha256:")
        assert chunk.embedding is not None
        assert len(chunk.embedding) == 384


def test_reingesting_same_bytes_produces_a_new_document_row(db_session):
    client = TestClient(app)
    content = (SAMPLES_DIR / "user-auth-service.md").read_bytes()

    first = client.post("/documents", files={"file": ("a.md", content, "text/markdown")})
    second = client.post("/documents", files={"file": ("a.md", content, "text/markdown")})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["content_hash"] == second.json()["content_hash"]


def test_reject_unsupported_file_type():
    client = TestClient(app)
    resp = client.post(
        "/documents",
        files={"file": ("evil.exe", b"not text", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_reject_empty_file():
    client = TestClient(app)
    resp = client.post("/documents", files={"file": ("empty.md", b"", "text/markdown")})
    assert resp.status_code == 400
