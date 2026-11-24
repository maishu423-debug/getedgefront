from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from edgefront_api.main import create_app
from edgefront_core.db import make_engine


def test_health_ok(engine: Engine) -> None:
    client = TestClient(create_app(engine))
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["service"] == "api"
    assert "generated_at" in body
    assert resp.headers["cache-control"] == "no-store"


def test_health_db_unreachable_returns_503() -> None:
    # Port 1 on localhost: connection refused immediately.
    bad = make_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    client = TestClient(create_app(bad))
    resp = client.get("/api/v1/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db"] == "unreachable"
