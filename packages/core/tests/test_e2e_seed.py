"""The e2e test-data seeder (v2 Phase 10): consistent with the real feeds, never for production."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core import db, e2e_seed, settings
from edgefront_core.db import session_scope
from edgefront_core.hf_store import qc_failed
from edgefront_core.models import HfObservation, MetarReport
from edgefront_core.registry import load_registry
from edgefront_core.seed import seed
from edgefront_core.timeutil import as_utc
from edgefront_core.units import f_to_c, f_to_c10

NOW = datetime(2026, 11, 28, 18, 7, tzinfo=UTC)


@pytest.fixture
def seeded(
    db_url: str, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> sessionmaker[Session]:
    with session_scope(session_factory) as s:
        seed(s, load_registry())
    monkeypatch.setenv("DATABASE_URL", db_url)
    settings.get_settings.cache_clear()
    db.get_engine.cache_clear()
    try:
        e2e_seed.seed_e2e(NOW)
    finally:
        settings.get_settings.cache_clear()
        db.get_engine.cache_clear()
    return session_factory


def test_cases_the_ui_tests_rely_on(seeded: sessionmaker[Session]) -> None:
    with session_scope(seeded) as s:
        latest = dict(
            s.execute(
                select(HfObservation.station_id, func.max(HfObservation.observed_at)).group_by(
                    HfObservation.station_id
                )
            ).all()
        )
        assert "KNYC" not in latest
        assert "KBKF" not in latest
        newest = as_utc(latest["KDFW"])
        assert timedelta(minutes=5) <= NOW - newest < timedelta(minutes=10)
        assert newest.minute % 5 == 0
        assert NOW - as_utc(latest["KSEA"]) > timedelta(minutes=45)  # stale
        spikes = [r for r in s.scalars(select(HfObservation)) if qc_failed(r.qc)]
        assert {r.station_id for r in spikes} == {"KDFW"}
        n_bos = s.scalar(select(func.count()).where(HfObservation.station_id == "KBOS"))
        n_dfw = s.scalar(select(func.count()).where(HfObservation.station_id == "KDFW"))
        assert n_dfw is not None
        assert n_bos == n_dfw - 8  # the 40-minute gap
        metars = s.scalars(select(MetarReport).where(MetarReport.station_id == "KNYC")).all()
        assert len(metars) >= 25
        assert {m.source for m in metars} == {"e2e-seed"}


def test_values_follow_the_verified_rounding(seeded: sessionmaker[Session]) -> None:
    """METAR T-group = nearest tenths °C of the whole-°F reading; 5-minute = nearest whole °C."""
    with session_scope(seeded) as s:
        for m in s.scalars(select(MetarReport).where(MetarReport.station_id == "KDFW")):
            f = e2e_seed.reading_f("KDFW", "America/Chicago", as_utc(m.observed_at))
            assert m.temp_c is not None
            assert int(m.temp_c * 10) == f_to_c10(f)
            assert m.temp_precision == "tenths"
        for r in s.scalars(select(HfObservation).where(HfObservation.station_id == "KLAX")):
            f = e2e_seed.reading_f("KLAX", "America/Los_Angeles", as_utc(r.observed_at))
            assert r.temp_c == f_to_c(f)


def test_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    settings.get_settings.cache_clear()
    try:
        assert e2e_seed.main(["--yes-this-is-a-test-database"]) == 2
    finally:
        settings.get_settings.cache_clear()
