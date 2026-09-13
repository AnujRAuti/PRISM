from fastapi.testclient import TestClient

from backend.app.main import app


def test_health():
    client = TestClient(app)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready():
    client = TestClient(app)
    r = client.get("/api/v1/ready")
    # SQLite default should be available in dev
    assert r.status_code in (200, 503)


def test_openapi_and_docs():
    client = TestClient(app)
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert "openapi" in r.json()

    r2 = client.get("/docs")
    assert r2.status_code == 200
