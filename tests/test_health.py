from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_ok_with_database_connected():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] is True
