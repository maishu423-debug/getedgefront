"""Nightly retention (§9) and the DATABASE_URL normalisation used on Railway."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from core_fixtures import FIXTURES
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.metar_ingest import store_reports, sync_high_events
from edgefront_core.model_store import upsert_run
from edgefront_core.models import DailyHighEvent, MetarReport, ModelRun, SourceHealth, Station
from edgefront_core.registry import load_registry
from edgefront_core.retention import KEEP_DAYS, run_retention
from edgefront_core.seed import seed
from edgefront_core.settings import Settings
from edgefront_core.timeutil import as_utc


def _load(factory: sessionmaker[Session]) -> None:
    corpus: list[dict[str, object]] = []
    for p in sorted((FIXTURES / "aviationweather").glob("metar_36h_batch*.json")):
        corpus += json.loads(Path(p).read_text(encoding="utf-8"))
    with session_scope(factory) as s:
        seed(s, load_registry())
    with session_scope(factory) as s:
        res = store_reports(s, corpus, datetime(2026, 11, 24, 16, 30, tzinfo=UTC))
        stations = {st.id: st for st in s.query(Station)}
        for sid, day in res.affected_days:
            sync_high_events(s, stations[sid], day)
        assert res.new > 100


def test_retention_prunes_only_beyond_400_days_and_logs_size(
    session_factory: sessionmaker[Session],
) -> None:
    _load(session_factory)
    with session_scope(session_factory) as s:
        n0 = s.execute(select(func.count()).select_from(MetarReport)).scalar_one()
        newest = as_utc(s.execute(select(func.max(MetarReport.observed_at))).scalar_one())
        oldest = as_utc(s.execute(select(func.min(MetarReport.observed_at))).scalar_one())
    # "now" such that the oldest 12 hours fall beyond the cutoff
    now = oldest + timedelta(days=KEEP_DAYS, hours=12)
    with session_scope(session_factory) as s:
        expect_gone = s.execute(
            select(func.count())
            .select_from(MetarReport)
            .where(MetarReport.observed_at < now - timedelta(days=KEEP_DAYS))
        ).scalar_one()
        events = s.execute(select(func.count()).select_from(DailyHighEvent)).scalar_one()
    assert events > 0
    assert 0 < expect_gone < n0
    assert newest > oldest

    out = run_retention(session_factory, now=now, warn_bytes=1)
    assert out.deleted["metar_reports"] == expect_gone
    assert out.rows["metar_reports"] == n0 - expect_gone
    assert out.db_bytes is not None
    assert out.db_bytes > 0
    assert out.warn is True  # 1-byte threshold
    with session_scope(session_factory) as s:
        # no high event may point at a deleted report
        dangling = s.execute(
            select(func.count())
            .select_from(DailyHighEvent)
            .where(~DailyHighEvent.report_id.in_(select(MetarReport.id)))
        ).scalar_one()
        assert dangling == 0
        h = s.get(SourceHealth, "retention")
        assert h is not None
        assert h.last_success_at is not None

    again = run_retention(session_factory, now=now)
    assert again.deleted["metar_reports"] == 0
    assert again.warn is False


def test_retention_keeps_latest_four_model_runs(session_factory: sessionmaker[Session]) -> None:
    from edgefront_core.timeutil import utcnow

    base = utcnow().replace(minute=0, second=0, microsecond=0)
    with session_scope(session_factory) as s:
        for h in range(6):
            upsert_run(s, "nbm", base - timedelta(hours=h), now=base)
    out = run_retention(session_factory)
    assert out.deleted["model_runs"] == 2
    with session_scope(session_factory) as s:
        assert s.execute(select(func.count()).select_from(ModelRun)).scalar_one() == 4


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgresql://u:p@postgres.railway.internal:5432/railway",
         "postgresql+psycopg://u:p@postgres.railway.internal:5432/railway"),
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("sqlite:///x.db", "sqlite:///x.db"),
    ],
)  # fmt: skip
def test_database_url_from_railway_is_normalised(given: str, expected: str) -> None:
    assert Settings(_env_file=None, database_url=given).database_url == expected


def test_retention_keeps_seven_days_of_hf_observations(
    session_factory: sessionmaker[Session],
) -> None:
    """v2 Phase 9 B4: 5-minute rows older than 7 days go, the file log after 4 days."""
    from edgefront_core.models import HfFile, HfObservation

    now = datetime(2026, 11, 28, 6, 0, tzinfo=UTC)
    with session_scope(session_factory) as s:
        seed(s, load_registry())
    with session_scope(session_factory) as s:
        for age_h in (1, 24 * 7 - 1, 24 * 7 + 1, 24 * 30):
            at = now - timedelta(hours=age_h)
            s.add(HfObservation(
                station_id="KDFW", observed_at=at, source_file="hfmetar.x.gz",
                fetched_at=at, ingested_at=at, updated_at=at, row_hash="0" * 64,
            ))  # fmt: skip
        for age_d in (1, 5):
            at = now - timedelta(days=age_d)
            s.add(HfFile(
                name=f"hfmetar.{age_d}.gz", modified_at=at, size_bytes=1, processed_at=at,
                records=0, our_rows=0,
            ))  # fmt: skip
    out = run_retention(session_factory, now=now)
    assert out.deleted["hf_observations"] == 2
    assert out.rows["hf_observations"] == 2
    assert out.deleted["hf_files"] == 1
    with session_scope(session_factory) as s:
        oldest = s.execute(select(func.min(HfObservation.observed_at))).scalar_one()
        assert as_utc(oldest) == now - timedelta(hours=24 * 7 - 1)
