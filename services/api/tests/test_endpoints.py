"""API endpoints against the real 36 h METAR corpus stored via the real ingest code."""

from __future__ import annotations

import glob
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from edgefront_api.main import create_app
from edgefront_core.climate import climate_date
from edgefront_core.db import session_scope
from edgefront_core.metar_ingest import store_reports, sync_high_events
from edgefront_core.models import Station
from edgefront_core.registry import load_registry
from edgefront_core.seed import seed
from edgefront_core.settings import Settings
from edgefront_core.source_health import record_success

REPO = Path(__file__).resolve().parents[3]
FIX = REPO / "packages" / "core" / "tests" / "fixtures" / "aviationweather"
NOW = datetime(2026, 11, 24, 16, 30, tzinfo=UTC)  # corpus ends 15:56Z
CFG = Settings(_env_file=None, app_env="test")


def corpus() -> list[dict[str, Any]]:
    import json

    items: list[dict[str, Any]] = []
    for p in sorted(glob.glob(str(FIX / "metar_36h_batch*.json"))):
        items += json.loads(Path(p).read_text(encoding="utf-8"))
    return items


@pytest.fixture
def loaded(engine: Engine, session_factory: sessionmaker[Session]) -> Engine:
    with session_scope(session_factory) as s:
        seed(s, load_registry(REPO / "data" / "stations.yaml"))
    with session_scope(session_factory) as s:
        res = store_reports(s, corpus(), NOW - timedelta(minutes=20))
        stations = {st.id: st for st in s.query(Station)}
        for sid, day in res.affected_days:
            sync_high_events(s, stations[sid], day)
        record_success(s, "metar", NOW - timedelta(minutes=2), last_item_time=res.latest_item_time)
    return engine


def client(engine: Engine, now: datetime = NOW) -> TestClient:
    return TestClient(create_app(engine, now=lambda: now, settings=CFG))


def test_board(loaded: Engine) -> None:
    body = client(loaded).get("/api/v1/stations").json()
    assert body["status"] == "ok"
    assert body["source"]["source"] == "aviationweather.gov/api/data/metar"
    assert body["source"]["last_success_at"] is not None
    rows = {r["id"]: r for r in body["stations"]}
    assert len(rows) == 28
    nyc = rows["KNYC"]
    assert nyc["zone_group"] == "Eastern"
    assert nyc["std_utc_offset_minutes"] == -300
    assert nyc["latest"]["observed_at"] == "2026-11-24T15:51:00Z"
    assert nyc["latest"]["temp_c"] == 8.3  # T00831044
    assert nyc["latest"]["temp_f"] == 47
    assert nyc["is_stale"] is False
    assert nyc["nws_today_high_f"] is None  # Phase 3
    assert nyc["high_so_far"]["value_f"] >= nyc["latest"]["temp_f"]
    assert nyc["climate_day"]["date"] == "2026-11-24"
    assert nyc["climate_day"]["start"] == "2026-11-24T05:00:00Z"
    assert {v["venue"] for v in nyc["venues"]} == {"kalshi"}
    assert all(v["verified"] is False for r in rows.values() for v in r["venues"])
    assert rows["KPHX"]["zone_group"] == "Mountain"
    assert rows["KSDF"]["zone_group"] == "Eastern"
    assert rows["KLAX"]["zone_group"] == "Pacific"


def test_board_high_so_far_matches_reports(loaded: Engine) -> None:
    """Independent check: KNYC high so far = max temp of today's KNYC reports (05Z onward)."""
    c = client(loaded)
    high = next(r for r in c.get("/api/v1/stations").json()["stations"] if r["id"] == "KNYC")[
        "high_so_far"
    ]
    reports = c.get("/api/v1/stations/KNYC/metars?hours=24").json()["reports"]
    today = [
        r["temp_c"]
        for r in reports
        if r["observed_at"] >= "2026-11-24T05:00:00Z"
        and not r["superseded"]
        and r["temp_c"] is not None
    ]
    assert high["value_c"] >= max(today)


def test_board_venue_filter(loaded: Engine) -> None:
    rows = client(loaded).get("/api/v1/stations?venue=polymarket").json()["stations"]
    assert {r["id"] for r in rows} == {
        "KLGA", "KATL", "KMIA", "KORD", "KDAL", "KAUS", "KHOU", "KBKF", "KLAX", "KSEA",
    }  # fmt: skip
    assert client(loaded).get("/api/v1/stations?venue=nope").status_code == 422


def test_board_no_data(engine: Engine, session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as s:
        seed(s, load_registry(REPO / "data" / "stations.yaml"))
    body = client(engine).get("/api/v1/stations").json()
    assert body["status"] == "no_data"
    assert all(r["latest"] is None and r["is_stale"] for r in body["stations"])


def test_station_meta_and_404(loaded: Engine) -> None:
    c = client(loaded)
    st = c.get("/api/v1/stations/knyc").json()["station"]
    assert st["id"] == "KNYC"
    assert st["name"] == "New York · Central Park"
    assert st["venues_verified"] is False
    assert st["local_time"].endswith("-05:00")
    assert c.get("/api/v1/stations/KZZZ").status_code == 404
    assert c.get("/api/v1/stations/K!@#").status_code in (404, 422)


def test_current_ok_stale_and_no_data(loaded: Engine, engine: Engine) -> None:
    body = client(loaded).get("/api/v1/stations/KNYC/current").json()
    assert body["status"] == "ok"
    latest = body["latest"]
    assert latest["raw_text"].startswith("METAR KNYC 241551Z")
    assert latest["wind_vrb"] is True
    assert latest["gust_kt"] == 18
    assert latest["rh_computed"] is not None
    assert body["high_so_far"]["kind"] in ("report", "max6h")

    later = client(loaded, NOW + timedelta(hours=3)).get("/api/v1/stations/KNYC/current").json()
    assert later["status"] == "stale"
    assert later["is_stale"] is True
    assert later["source"]["last_success_at"] is not None


def test_metars_newest_first_and_superseded(
    loaded: Engine, session_factory: sessionmaker[Session]
) -> None:
    c = client(loaded)
    reports = c.get("/api/v1/stations/KLGA/metars?hours=36").json()["reports"]
    times = [r["observed_at"] for r in reports]
    assert times == sorted(times, reverse=True)
    assert any(r["is_correction"] for r in reports)
    # Store a fake later correction of the latest report → the original becomes superseded.
    latest = reports[0]
    with session_scope(session_factory) as s:
        raw = latest["raw_text"].replace("KLGA ", "KLGA ", 1).replace("Z ", "Z COR ", 1)
        store_reports(
            s,
            [
                {
                    "rawOb": raw,
                    "obsTime": int(datetime.fromisoformat(latest["observed_at"]).timestamp()),
                }
            ],
            NOW,
        )
    again = client(loaded).get("/api/v1/stations/KLGA/metars?hours=36").json()["reports"]
    assert sum(1 for r in again if r["superseded"]) >= 1
    assert c.get("/api/v1/stations/KLGA/metars?hours=99").status_code == 422


def test_observed_series_and_gaps(loaded: Engine) -> None:
    body = client(loaded).get("/api/v1/stations/KMSP/observed?hours=24").json()
    pts = body["points"]
    assert body["gap_minutes"] == 90
    assert [p["observed_at"] for p in pts] == sorted(p["observed_at"] for p in pts)
    assert all(p["rh_computed"] is None or 0 < p["rh_computed"] <= 100 for p in pts)
    assert body["gaps"] == []  # hourly reports, no gap > 90 min
    # Three hours later the tail of the window has no reports: that is a gap, never bridged.
    later = (
        client(loaded, NOW + timedelta(hours=3))
        .get("/api/v1/stations/KMSP/observed?hours=6")
        .json()
    )
    assert later["gaps"]
    assert later["gaps"][-1]["minutes"] > 90
    assert client(loaded).get("/api/v1/stations/KMSP/observed?hours=12").status_code == 422


def test_feed_new_highs(loaded: Engine) -> None:
    body = client(loaded).get("/api/v1/feed/new-highs?limit=5").json()
    ev = body["events"]
    assert 0 < len(ev) <= 5
    assert [e["observed_at"] for e in ev] == sorted((e["observed_at"] for e in ev), reverse=True)
    assert all(e["to_c"] > e["from_c"] and e["to_f"] >= e["from_f"] for e in ev)
    assert client(loaded).get("/api/v1/feed/new-highs?limit=500").status_code == 422


def test_status(loaded: Engine) -> None:
    body = client(loaded).get("/api/v1/status").json()
    by = {x["key"]: x for x in body["sources"]}
    assert by["metar"]["healthy"] is True
    assert by["metar"]["schedule_seconds"] == 180
    assert by["worker"]["healthy"] is False  # no heartbeat in this test DB
    later = client(loaded, NOW + timedelta(minutes=10)).get("/api/v1/status").json()
    assert {x["key"]: x for x in later["sources"]}["metar"]["healthy"] is False  # > 3 x 180 s


def test_cache_headers_and_etag(loaded: Engine) -> None:
    c = client(loaded)
    r1 = c.get("/api/v1/stations")
    assert r1.headers["cache-control"] == "public, max-age=30"
    etag = r1.headers["etag"]
    r2 = c.get("/api/v1/stations", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    # generated_at differs between requests but must not change the ETag.
    ticking = iter([NOW, NOW + timedelta(seconds=5)])
    c2 = TestClient(create_app(loaded, now=lambda: next(ticking), settings=CFG))
    e1 = c2.get("/api/v1/status").headers["etag"]
    e2 = c2.get("/api/v1/status").headers["etag"]
    assert e1 == e2
    assert c.get("/api/v1/health").headers["cache-control"] == "no-store"


def test_new_high_event_climate_day_is_lst(loaded: Engine) -> None:
    ev = client(loaded).get("/api/v1/feed/new-highs?limit=50").json()["events"]
    for e in ev:
        st_tz = {"KNYC": "America/New_York"}.get(e["station_id"])
        if st_tz:
            obs = datetime.fromisoformat(e["observed_at"])
            assert e["climate_date"] == climate_date(obs, st_tz).isoformat()
