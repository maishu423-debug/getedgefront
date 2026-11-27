from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

import edgefront_worker.jobs as jobs
from edgefront_core.db import session_scope
from edgefront_core.models import SourceHealth
from edgefront_worker.main import build_scheduler


def test_metar_job_never_raises_and_records_failure(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Boom:
        def __enter__(self) -> Boom:
            return self

        def __exit__(self, *a: object) -> None:
            return None

    def fail(*_a: object, **_k: object) -> None:
        raise RuntimeError("upstream down")

    monkeypatch.setattr(jobs, "make_client", lambda: Boom())
    monkeypatch.setattr(jobs, "run_metar_ingest", fail)
    jobs.metar_job(session_factory)  # must not raise


def test_scheduler_has_all_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("CONTACT_EMAIL", "ops@example.org")  # placeholder; no request is made
    from edgefront_core import db, settings

    settings.get_settings.cache_clear()
    db.get_engine.cache_clear()
    try:
        sched = build_scheduler()
        ids = {j.id for j in sched.get_jobs()}
        assert ids == {
            "heartbeat",
            "metar",
            "cli",
            "dsm",
            "forecast",
            "models_text",
            "models_grib",
            "retention",
            "native_unit_check",
        }
    finally:
        settings.get_settings.cache_clear()
        db.get_engine.cache_clear()


def test_failure_is_recorded_by_ingest(session_factory: sessionmaker[Session]) -> None:
    import httpx

    from edgefront_core.metar_ingest import run_metar_ingest

    def down(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(down))
    with session_scope(session_factory) as s:
        from edgefront_core.models import Station

        s.add(Station(id="KNYC", name="x", city="x", state="NY", tz="America/New_York"))
    with pytest.raises(Exception, match="503"):
        run_metar_ingest(session_factory, client, sleep=lambda _s: None)
    with session_scope(session_factory) as s:
        h = s.get(SourceHealth, "metar")
        assert h is not None
        assert h.last_error is not None
        assert "503" in h.last_error
        assert h.last_success_at is None


def test_ci_mode_schedules_no_upstream_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("CONTACT_EMAIL", "")
    monkeypatch.setenv("WORKER_UPSTREAM_ENABLED", "false")
    from edgefront_core import db, settings

    settings.get_settings.cache_clear()
    db.get_engine.cache_clear()
    try:
        ids = {j.id for j in build_scheduler().get_jobs()}
        assert ids == {"heartbeat", "retention", "native_unit_check"}  # no upstream traffic
    finally:
        settings.get_settings.cache_clear()
        db.get_engine.cache_clear()
