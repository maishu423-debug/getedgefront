"""X-Internal-Token on /api/v1/internal/* only (v2 Phase 7 C)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from edgefront_api.main import create_app
from edgefront_core.settings import Settings


def client(engine: Engine, token: str) -> TestClient:
    cfg = Settings(_env_file=None, app_env="test", internal_api_token=token)
    return TestClient(create_app(engine, settings=cfg))


def test_internal_route_requires_the_token(engine: Engine) -> None:
    c = client(engine, "s3cret-token")
    assert c.get("/api/v1/internal/ping").status_code == 403
    assert c.get("/api/v1/internal/ping", headers={"X-Internal-Token": "wrong"}).status_code == 403
    ok = c.get("/api/v1/internal/ping", headers={"X-Internal-Token": "s3cret-token"})
    assert ok.status_code == 200
    assert ok.json() == {"ok": True}
    # unknown internal paths are refused before routing, so nothing leaks about what exists
    assert c.get("/api/v1/internal/nope").status_code == 403


def test_fails_closed_without_a_configured_token(engine: Engine) -> None:
    c = client(engine, "")
    assert c.get("/api/v1/internal/ping", headers={"X-Internal-Token": ""}).status_code == 403
    assert c.get("/api/v1/internal/ping", headers={"X-Internal-Token": "x"}).status_code == 403


def test_public_routes_unaffected(engine: Engine) -> None:
    c = client(engine, "s3cret-token")
    assert c.get("/api/v1/health").status_code in (200, 503)
    assert c.get("/api/v1/internalx").status_code == 404  # prefix match is exact
