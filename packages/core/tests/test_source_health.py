from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import ping, session_scope
from edgefront_core.models import SourceHealth
from edgefront_core.source_health import record_failure, record_success

T0 = datetime(2026, 11, 24, 21, 0, tzinfo=UTC)


def test_migration_creates_source_health(engine: Engine) -> None:
    ping(engine)
    assert "source_health" in inspect(engine).get_table_names()


def test_record_success_inserts_then_updates(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as s:
        record_success(s, "worker", T0, notes="heartbeat")
    with session_scope(session_factory) as s:
        record_success(s, "worker", T0 + timedelta(minutes=1))

    with session_scope(session_factory) as s:
        rows = s.query(SourceHealth).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.last_success_at is not None
        assert row.last_success_at.replace(tzinfo=UTC) == T0 + timedelta(minutes=1)
        assert row.notes == "heartbeat"  # not overwritten when not passed


def test_record_failure_keeps_last_success(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as s:
        record_success(s, "metar", T0)
    with session_scope(session_factory) as s:
        record_failure(s, "metar", T0 + timedelta(minutes=3), "HTTP 503")

    with session_scope(session_factory) as s:
        row = s.get(SourceHealth, "metar")
        assert row is not None
        assert row.last_error == "HTTP 503"
        assert row.last_success_at is not None
        assert row.last_success_at.replace(tzinfo=UTC) == T0
