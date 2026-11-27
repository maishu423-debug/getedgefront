"""v2 Phase 9 B5: the `hfmetar` job against real (cropped) MADIS files and a mocked LDM API."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from core_fixtures import FIXTURES
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.hf_store import HfReading, upsert_readings
from edgefront_core.models import HfFile, HfObservation, SourceHealth
from edgefront_core.registry import load_registry
from edgefront_core.seed import seed
from edgefront_core.timeutil import as_utc
from edgefront_worker.hfmetar import (
    HfmetarIngest,
    _temp,
    check_base_url,
    gunzip_capped,
    parse_file,
    parse_listing,
)

HF = FIXTURES / "hfmetar"
F15 = (HF / "hfmetar.20261127_1500.gz").read_bytes()
F17 = (HF / "hfmetar.20261127_1700.gz").read_bytes()
F17B = (HF / "hfmetar.20261127_1700.v2.gz").read_bytes()
NOW = datetime(2026, 11, 27, 18, 14, tzinfo=UTC)
BASE = "https://ldm.example.org"
OURS = {st.id for st in load_registry()}


def _listing(*files: tuple[str, int, str]) -> dict[str, object]:
    return {"files": [{"name": n, "size_bytes": s, "modified_at": m} for n, s, m in files]}


class FakeLdm:
    """The owner's madis-api behind Caddy: /health, the file list, the files."""

    def __init__(self) -> None:
        self.health_status = 200
        self.listing: dict[str, object] = _listing()
        self.files: dict[str, bytes] = {}
        self.requests: list[httpx.Request] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        path = req.url.path
        if path == "/health":
            return httpx.Response(self.health_status, json={"status": "ok"})
        if req.headers.get("Authorization") != "Bearer test-token":
            return httpx.Response(401)
        if path == "/api/v1/hfmetar/files":
            return httpx.Response(200, json=self.listing)
        name = path.rsplit("/", 1)[-1]
        if name in self.files:
            return httpx.Response(
                200,
                content=self.files[name],
                headers={"Last-Modified": "Fri, 27 Nov 2026 18:11:43 GMT"},
            )
        return httpx.Response(404)

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> sessionmaker[Session]:
    with session_scope(session_factory) as s:
        seed(s, load_registry())
    return session_factory


def _ingest(ldm: FakeLdm, now: datetime = NOW, **kw: int) -> HfmetarIngest:
    client = httpx.Client(transport=httpx.MockTransport(ldm))
    return HfmetarIngest(client, BASE, "test-token", now=lambda: now, sleep=lambda _s: None, **kw)


def _count(factory: sessionmaker[Session]) -> int:
    with session_scope(factory) as s:
        return int(s.scalar(select(func.count()).select_from(HfObservation)) or 0)


# ---------------------------------------------------------------- parsing


def test_parse_real_file_registry_stations_whole_celsius() -> None:
    p = parse_file(F15, OURS)
    assert p.records == 312  # the fixture is cropped to our stations already
    assert len(p.readings) == 312
    assert p.duplicates == 0
    assert p.skipped_provider == 0
    assert p.off_grid == 0
    assert p.raw_bytes > 50_000
    per = Counter(r.station_id for r in p.readings)
    assert "KNYC" not in per  # not an FAA ASOS: not in the feed (docs/formats/hfmetar.md)
    assert "KBKF" not in per
    assert per["KDFW"] == 12  # every 5 minutes, :00 … :55
    kdfw = sorted((r for r in p.readings if r.station_id == "KDFW"), key=lambda r: r.observed_at)
    assert [r.observed_at.minute for r in kdfw] == list(range(0, 60, 5))
    assert all(r.observed_at.hour == 15 for r in kdfw)
    for r in p.readings:
        assert r.temp_precision in ("whole_c", None)
        if r.temp_c is not None:
            assert r.temp_c == r.temp_c.to_integral_value()
        assert r.qc["temperature"]["dd"] in {"V", "Q", "Z", "S", "C", "X", "B", "G", None}
        if r.wind_kt is not None:
            assert r.wind_kt >= 0
        if r.altim_inhg is not None:
            assert Decimal("27") < r.altim_inhg < Decimal("32")
        assert r.received_at is not None
        assert r.received_at >= r.observed_at


def test_parse_only_keeps_the_stations_asked_for() -> None:
    p = parse_file(F15, {"KDFW", "KLAX"})
    assert p.records == 312
    assert {r.station_id for r in p.readings} == {"KDFW", "KLAX"}


@pytest.mark.parametrize(
    ("kelvin", "value", "precision", "flagged"),
    [
        (288.1499938964844, Decimal("15"), "whole_c", False),  # float32 of 15 °C
        (273.1499938964844, Decimal("0"), "whole_c", False),
        (250.1499938964844, Decimal("-23"), "whole_c", False),
        (288.25, Decimal("15.1"), "tenths_c", False),
        (288.40, Decimal("15.25"), "off_grid", True),  # neither grid: kept, flagged, not guessed
        (None, None, None, False),
    ],
)
def test_temperature_snapping(
    kelvin: float | None, value: Decimal | None, precision: str | None, flagged: bool
) -> None:
    off: dict[str, float] = {}
    assert _temp(kelvin, off, "temperature") == (value, precision)
    assert ("temperature" in off) is flagged


def test_gunzip_refuses_oversized_files() -> None:
    with pytest.raises(ValueError, match="larger than"):
        gunzip_capped(F15, limit=1000)


def test_listing_drops_unexpected_names() -> None:
    files = parse_listing(_listing(
        ("hfmetar.20261127_1700.gz", 10, "2026-11-27T18:06:34.875254+00:00"),
        ("../../etc/passwd", 1, "2026-11-27T18:06:34+00:00"),
        ("hfmetar.20261127_1700.gz?x=1", 1, "2026-11-27T18:06:34+00:00"),
    ))  # fmt: skip
    assert [f.name for f in files] == ["hfmetar.20261127_1700.gz"]
    assert files[0].hour == datetime(2026, 11, 27, 17, tzinfo=UTC)


def test_token_only_over_https() -> None:
    assert check_base_url("https://ldm.getedgefront.com/") == "https://ldm.getedgefront.com"
    assert check_base_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
    with pytest.raises(ValueError, match="https"):
        check_base_url("http://ldm.getedgefront.com")
    with pytest.raises(ValueError, match="TOKEN"):
        HfmetarIngest(httpx.Client(), BASE, "")


# ---------------------------------------------------------------- the job


def test_ingest_dedupes_and_handles_a_rewrite(seeded: sessionmaker[Session]) -> None:
    ldm = FakeLdm()
    ldm.listing = _listing(
        ("hfmetar.20261127_1700.gz", len(F17), "2026-11-27T18:06:34.875254+00:00"),
        ("hfmetar.20261127_1500.gz", len(F15), "2026-11-27T17:42:02.543997+00:00"),
    )
    ldm.files = {"hfmetar.20261127_1700.gz": F17, "hfmetar.20261127_1500.gz": F15}
    job = _ingest(ldm)

    m1 = job.run(seeded)
    assert (m1.files_processed, m1.new, m1.revised, m1.errors) == (2, 312 + 295, 0, [])
    assert _count(seeded) == 607
    assert ldm.paths()[:2] == ["/health", "/api/v1/hfmetar/files"]
    assert ldm.paths()[2:] == ["/api/v1/hfmetar/hfmetar.20261127_1700.gz",  # newest first
                               "/api/v1/hfmetar/hfmetar.20261127_1500.gz"]  # fmt: skip
    assert "Authorization" not in ldm.requests[0].headers  # /health needs no token

    # unchanged listing: nothing downloaded, nothing written
    ldm.requests.clear()
    m2 = job.run(seeded)
    assert m2.files_changed == 0
    assert ldm.paths() == ["/health", "/api/v1/hfmetar/files"]
    assert _count(seeded) == 607

    # the current hour is rewritten: 3 new rows for our stations, QC revised, values unchanged
    ldm.listing = _listing(
        ("hfmetar.20261127_1700.gz", len(F17B), "2026-11-27T18:11:43.278568+00:00"),
        ("hfmetar.20261127_1500.gz", len(F15), "2026-11-27T17:42:02.543997+00:00"),
    )
    ldm.files["hfmetar.20261127_1700.gz"] = F17B
    m3 = job.run(seeded)
    assert m3.files_processed == 1
    assert m3.new == 3
    assert m3.revised == 0  # MADIS never changed a measured value (B2 finding)
    assert m3.qc_changed > 0
    assert m3.new + m3.qc_changed + m3.unchanged == 298
    with session_scope(seeded) as s:
        assert s.scalar(select(func.count()).select_from(HfObservation)) == 312 + 298
        assert s.scalar(select(func.max(HfObservation.revision))) == 0
        dup = s.execute(
            select(HfObservation.station_id, HfObservation.observed_at, func.count())
            .group_by(HfObservation.station_id, HfObservation.observed_at)
            .having(func.count() > 1)
        ).all()
        assert dup == []
        f = s.get(HfFile, "hfmetar.20261127_1700.gz")
        assert f is not None
        assert f.size_bytes == len(F17B)
        assert f.our_rows == 298
        # first-seen stamps kept for old rows; new rows carry the rewrite's file time
        new_rows = s.scalars(
            select(HfObservation).where(
                HfObservation.source_file == "hfmetar.20261127_1700.gz",
                HfObservation.observed_at >= datetime(2026, 11, 27, 17, 50, tzinfo=UTC),
            )
        ).all()
        assert new_rows
        h = s.get(SourceHealth, "hfmetar")
        assert h is not None
        assert h.last_success_at is not None
        assert h.last_item_time is not None
        assert as_utc(h.last_item_time) == max(as_utc(r.observed_at) for r in new_rows)


def test_revision_bumps_only_when_a_value_changes(seeded: sessionmaker[Session]) -> None:
    at = datetime(2026, 11, 27, 15, 0, tzinfo=UTC)
    base = HfReading("KDFW", at, temp_c=Decimal(17), temp_precision="whole_c",
                     qc={"temperature": {"dd": "Z"}})  # fmt: skip
    kw: dict[str, Any] = {"source_file": "a.gz", "file_modified_at": at, "fetched_at": at}
    with session_scope(seeded) as s:
        assert upsert_readings(s, [base], now=at, **kw).new == 1
    later = at + timedelta(minutes=5)
    with session_scope(seeded) as s:  # QC only
        qc = HfReading("KDFW", at, temp_c=Decimal(17), temp_precision="whole_c",
                       qc={"temperature": {"dd": "V"}})  # fmt: skip
        r = upsert_readings(s, [qc], now=later, **kw)
        assert (r.qc_changed, r.revised) == (1, 0)
    with session_scope(seeded) as s:  # a value: the newer one is kept, revision counts it
        val = HfReading("KDFW", at, temp_c=Decimal(18), temp_precision="whole_c",
                        qc={"temperature": {"dd": "V"}})  # fmt: skip
        r = upsert_readings(s, [val], now=later + timedelta(minutes=5), **kw)
        assert r.revised == 1
    with session_scope(seeded) as s:
        row = s.get(HfObservation, ("KDFW", at))
        assert row is not None
        assert row.temp_c == Decimal(18)
        assert row.revision == 1
        assert row.qc is not None
        assert row.qc["temperature"]["dd"] == "V"
        assert as_utc(row.ingested_at) == at  # first-seen stamps never move
        assert as_utc(row.updated_at) == later + timedelta(minutes=5)


def test_backfill_window_and_per_run_cap(seeded: sessionmaker[Session]) -> None:
    ldm = FakeLdm()
    ldm.listing = _listing(
        ("hfmetar.20261127_1700.gz", len(F17), "2026-11-27T18:06:34+00:00"),
        ("hfmetar.20261127_1500.gz", len(F15), "2026-11-27T17:42:02+00:00"),
        ("hfmetar.20261125_1500.gz", 1, "2026-11-25T17:42:02+00:00"),  # beyond 24 h
    )
    ldm.files = {"hfmetar.20261127_1700.gz": F17, "hfmetar.20261127_1500.gz": F15}
    job = _ingest(ldm, max_files=1)
    m = job.run(seeded)
    assert (m.files_changed, m.files_processed, m.files_deferred) == (2, 1, 1)
    assert "/api/v1/hfmetar/hfmetar.20261125_1500.gz" not in ldm.paths()
    with session_scope(seeded) as s:
        assert [f.name for f in s.scalars(select(HfFile))] == ["hfmetar.20261127_1700.gz"]
    m = job.run(seeded)  # the deferred file comes next
    assert (m.files_changed, m.files_processed) == (1, 1)


def test_bad_file_is_recorded_and_others_still_load(seeded: sessionmaker[Session]) -> None:
    ldm = FakeLdm()
    ldm.listing = _listing(
        ("hfmetar.20261127_1700.gz", 9, "2026-11-27T18:06:34+00:00"),
        ("hfmetar.20261127_1500.gz", len(F15), "2026-11-27T17:42:02+00:00"),
    )
    ldm.files = {"hfmetar.20261127_1700.gz": b"not gzip!", "hfmetar.20261127_1500.gz": F15}
    m = _ingest(ldm).run(seeded)
    assert (m.files_processed, m.files_failed) == (1, 1)
    assert _count(seeded) == 312
    with session_scope(seeded) as s:
        h = s.get(SourceHealth, "hfmetar")
        assert h is not None
        assert h.last_error is not None
        assert "hfmetar.20261127_1700.gz" in h.last_error
        assert s.get(HfFile, "hfmetar.20261127_1700.gz") is None  # retried next run


def test_alerts_health_failure_and_no_new_readings(
    seeded: sessionmaker[Session], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="edgefront.worker.hfmetar")
    ldm = FakeLdm()
    ldm.health_status = 503
    clock = [NOW]
    client = httpx.Client(transport=httpx.MockTransport(ldm))
    job = HfmetarIngest(client, BASE, "test-token", now=lambda: clock[0], sleep=lambda _s: None)

    job.run(seeded)
    assert ldm.paths() == ["/health", "/health"]  # retried once; no file list without health
    alerts = [r for r in caplog.records if getattr(r, "alert", None) == "ldm_health"]
    assert len(alerts) == 1
    assert alerts[0].levelno == logging.ERROR
    with session_scope(seeded) as s:
        h = s.get(SourceHealth, "hfmetar")
        assert h is not None
        assert "/health" in (h.last_error or "")

    clock[0] = NOW + timedelta(minutes=1)
    job.run(seeded)  # still down: not logged again within the hour
    assert len([r for r in caplog.records if getattr(r, "alert", None) == "ldm_health"]) == 1

    # /health back, but the feed is empty: no new readings → the second alert
    ldm.health_status = 200
    caplog.clear()
    job.run(seeded)
    keys = [(getattr(r, "alert", None), r.levelno) for r in caplog.records]
    assert ("ldm_health", logging.WARNING) in keys  # resolved
    assert ("no_new_readings", logging.ERROR) in keys

    # data flows again: resolved
    ldm.listing = _listing(("hfmetar.20261127_1500.gz", len(F15), "2026-11-27T17:42:02+00:00"))
    ldm.files = {"hfmetar.20261127_1500.gz": F15}
    caplog.clear()
    job.run(seeded)
    keys = [(getattr(r, "alert", None), r.levelno) for r in caplog.records]
    assert ("no_new_readings", logging.WARNING) in keys
    run_log = [r for r in caplog.records if r.getMessage() == "hfmetar ingest"][-1]
    assert run_log.count_new == 312  # type: ignore[attr-defined]
    assert hasattr(run_log, "process_peak_rss_mb")


def test_scheduler_runs_hfmetar_only_when_enabled_and_safe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from edgefront_core import db, settings
    from edgefront_worker.main import build_scheduler

    monkeypatch.chdir(tmp_path)  # no .env from the repo
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("CONTACT_EMAIL", "ops@example.org")  # placeholder; no request is made
    monkeypatch.setenv("MADIS_API_TOKEN", "t")

    def ids(**env: str) -> set[str]:
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        settings.get_settings.cache_clear()
        db.get_engine.cache_clear()
        try:
            return {j.id for j in build_scheduler().get_jobs()}
        finally:
            settings.get_settings.cache_clear()
            db.get_engine.cache_clear()

    assert "hfmetar" not in ids(HF_INGEST_ENABLED="false", LDM_API_BASE_URL=BASE)
    assert "hfmetar" in ids(HF_INGEST_ENABLED="true", LDM_API_BASE_URL=BASE)
    assert "hfmetar" not in ids(HF_INGEST_ENABLED="true", LDM_API_BASE_URL="http://ldm.example.org")
