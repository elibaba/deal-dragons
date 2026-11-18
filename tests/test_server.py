"""Smoke test: the production FastAPI entrypoint builds and serves /healthz."""

from fastapi.testclient import TestClient


def test_server_builds_and_health_check():
    import server

    client = TestClient(server.app)
    assert client.get("/healthz").json() == {"status": "ok"}
    assert "deal_dragons" in client.get("/list-apps").json()
