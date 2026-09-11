"""Test setup: point the app at a dedicated `archlens_test` database (never
the dev database), apply the real Alembic migration to it, and truncate
all tables before every test for isolation.

The env vars below MUST be set before `app.config`/`app.db`/`app.models`
are first imported anywhere in the test session (those modules read
settings at import time), so this happens at conftest module level, not
inside a fixture.
"""

import os

os.environ.setdefault("POSTGRES_DB", "archlens_test")
os.environ.setdefault("STORAGE_DIR", "./data/storage_test")

from pathlib import Path  # noqa: E402

import psycopg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = _PROJECT_ROOT / "data" / "samples"
SAMPLE_FILENAMES = ["payment-service.md", "user-auth-service.md", "data-pipeline.md"]

PUBLIC_CORPUS_DIR = _PROJECT_ROOT / "data" / "samples" / "public"
# Real public documents (see data/samples/public/SOURCES.md for URL +
# license per file) — SOURCES.md itself is metadata, not corpus content.
PUBLIC_CORPUS_FILENAMES = [
    "kubernetes-pod-security-standards.md",
    "nist-csf-functions.md",
    "owasp-a01-broken-access-control.md",
    "owasp-a02-cryptographic-failures.md",
]

_TABLES_IN_DEPENDENCY_ORDER = (
    "finding_evidence",
    "findings",
    "components",
    "chunks",
    "documents",
    "compliance_controls",
    "audit_log",
)


def _ensure_database_exists(settings) -> None:
    admin_conn = psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        dbname="postgres",
        autocommit=True,
    )
    try:
        with admin_conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.postgres_db,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{settings.postgres_db}"')
    finally:
        admin_conn.close()


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    settings = get_settings()
    assert settings.postgres_db.endswith("_test"), (
        "refusing to run tests against a non-test database "
        f"(POSTGRES_DB={settings.postgres_db!r})"
    )
    _ensure_database_exists(settings)

    alembic_cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {', '.join(_TABLES_IN_DEPENDENCY_ORDER)} CASCADE"))
    yield


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def ingested_samples(client: TestClient) -> dict[str, str]:
    """Ingest all three synthetic sample docs; return filename -> document_id."""
    ids: dict[str, str] = {}
    for filename in SAMPLE_FILENAMES:
        content = (SAMPLES_DIR / filename).read_bytes()
        resp = client.post("/documents", files={"file": (filename, content, "text/markdown")})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ingested"
        ids[filename] = body["id"]
    return ids


@pytest.fixture()
def ingested_public_corpus(client: TestClient) -> dict[str, str]:
    """Ingest the real public-document corpus (data/samples/public/,
    see SOURCES.md); return filename -> document_id."""
    ids: dict[str, str] = {}
    for filename in PUBLIC_CORPUS_FILENAMES:
        content = (PUBLIC_CORPUS_DIR / filename).read_bytes()
        resp = client.post("/documents", files={"file": (filename, content, "text/markdown")})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ingested"
        ids[filename] = body["id"]
    return ids
