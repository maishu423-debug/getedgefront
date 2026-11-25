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


def test_dual_stack_socket_accepts_ipv4_and_ipv6() -> None:
    import socket

    from edgefront_api.serve import dual_stack_socket

    srv = dual_stack_socket(0)
    try:
        srv.listen()
        port = srv.getsockname()[1]
        assert srv.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY) == 0
        for family, addr in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
            with socket.socket(family, socket.SOCK_STREAM) as c:
                c.settimeout(2)
                c.connect((addr, port))
                conn, _ = srv.accept()
                conn.close()
    finally:
        srv.close()
