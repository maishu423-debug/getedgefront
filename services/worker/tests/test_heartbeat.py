from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import make_engine, make_sessionmaker, session_scope
from edgefront_core.models import SourceHealth
from edgefront_worker.heartbeat import heartbeat

T0 = datetime(2026, 11, 24, 21, 0, tzinfo=UTC)


def test_heartbeat_writes_source_health(session_factory: sessionmaker[Session]) -> None:
    times = iter([T0, T0 + timedelta(minutes=1)])
    assert heartbeat(session_factory, now=lambda: next(times))
    assert heartbeat(session_factory, now=lambda: next(times))

    with session_scope(session_factory) as s:
        row = s.get(SourceHealth, "worker")
        assert row is not None
        assert row.last_success_at is not None
        assert row.last_success_at.replace(tzinfo=UTC) == T0 + timedelta(minutes=1)
        assert row.last_error is None


def test_heartbeat_logs_json(
    session_factory: sessionmaker[Session], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="edgefront.worker.heartbeat")
    heartbeat(session_factory, now=lambda: T0)
    rec = next(r for r in caplog.records if r.getMessage() == "heartbeat")
    assert rec.__dict__["source"] == "worker"
    assert isinstance(rec.__dict__["duration_ms"], int)
    json.dumps(rec.__dict__["at"])  # serialisable


def test_heartbeat_survives_db_down() -> None:
    bad = make_sessionmaker(make_engine("postgresql+psycopg://x:x@127.0.0.1:1/x"))
    assert heartbeat(bad, now=lambda: T0) is False
