"""v2 Phase 9 B6/B7/B8: internal 5-minute endpoints (X-Internal-Token) and the /status block."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from edgefront_api.main import create_app
from edgefront_core.db import session_scope
from edgefront_core.hf_store import HfReading, upsert_readings
from edgefront_core.models import HfFile, MetarReport
from edgefront_core.registry import load_registry
from edgefront_core.seed import seed
from edgefront_core.settings import Settings
from edgefront_core.source_health import record_success

TOKEN = "s3cret-token"  # noqa: S105 - test value
H = {"X-Internal-Token": TOKEN}
NOW = datetime(2026, 11, 27, 21, 2, tzinfo=UTC)  # KDFW climate day 2026-11-27: 06:00Z → 06:00Z
PATHS = ("/api/v1/internal/stations/KDFW/hf", "/api/v1/internal/stations/KDFW/hf-current",
         "/api/v1/internal/map")  # fmt: skip


def _read(at: datetime, c: int | None, dd: str = "V", sid: str = "KDFW") -> HfReading:
    return HfReading(
        sid, at, received_at=at + timedelta(seconds=142),
        temp_c=None if c is None else Decimal(c), temp_precision=None if c is None else "whole_c",
        dewpt_c=Decimal(9), wind_dir_deg=180, wind_kt=12, gust_kt=None,
        altim_inhg=Decimal("30.07"), vis_mi=Decimal(10), precip_in=Decimal(0),
        qc={"temperature": {"dd": dd, "qca": 123, "qcr": 0 if dd == "V" else 16}},
    )  # fmt: skip


@pytest.fixture
def loaded(engine: Engine, session_factory: sessionmaker[Session]) -> Engine:
    with session_scope(session_factory) as s:
        seed(s, load_registry())
    start = datetime(2026, 11, 27, 6, 0, tzinfo=UTC)
    kdfw: dict[datetime, HfReading] = {}
    t = start
    while t <= NOW - timedelta(minutes=2):  # every 5 minutes, 06:00Z through 21:00Z
        kdfw[t] = _read(t, 10 + min(10, (t - start).seconds // 3600))  # 10 °C rising to 20 °C
        t += timedelta(minutes=5)
    t2045 = datetime(2026, 11, 27, 20, 45, tzinfo=UTC)
    t2050 = datetime(2026, 11, 27, 20, 50, tzinfo=UTC)
    kdfw[t2045] = _read(t2045, None)  # missing temperature
    kdfw[t2050] = _read(t2050, 30, dd="Q")  # questioned spike
    rows = [
        *kdfw.values(),
        _read(NOW - timedelta(minutes=7), 16, sid="KLAX"),
        _read(NOW - timedelta(hours=3), 14, sid="KSEA"),  # stale
    ]
    with session_scope(session_factory) as s:
        upsert_readings(
            s,
            rows,
            source_file="hfmetar.20261127_2000.gz",
            file_modified_at=NOW - timedelta(seconds=40),
            fetched_at=NOW - timedelta(seconds=20),
            now=NOW - timedelta(seconds=19),
        )
        s.add(
            HfFile(
                name="hfmetar.20261127_2000.gz",
                modified_at=NOW - timedelta(seconds=40),
                size_bytes=1_250_000,
                processed_at=NOW - timedelta(seconds=19),
                records=11686,
                our_rows=298,
            )
        )
        s.add(
            MetarReport(
                station_id="KDFW",
                report_type="METAR",
                observed_at=datetime(2026, 11, 27, 20, 53, tzinfo=UTC),
                raw_text="METAR KDFW 272053Z 18012KT 10SM CLR 17/09 A3007 RMK AO2 T01720089",
                raw_hash="h1",
                temp_c=Decimal("17.2"),
                temp_precision="tenths",
                source="t",
                fetched_at=NOW,
            )
        )
        record_success(s, "hfmetar", NOW - timedelta(seconds=19), last_item_time=NOW)
    return engine


def client(engine: Engine, now: datetime = NOW) -> TestClient:
    cfg = Settings(_env_file=None, app_env="test", internal_api_token=TOKEN)
    return TestClient(create_app(engine, now=lambda: now, settings=cfg))


def test_every_hf_route_needs_the_internal_token(loaded: Engine) -> None:
    c = client(loaded)
    for p in PATHS:
        assert c.get(p).status_code == 403
        assert c.get(p, headers={"X-Internal-Token": "wrong"}).status_code == 403
        ok = c.get(p, headers=H)
        assert ok.status_code == 200, p
        assert ok.headers["Cache-Control"] == "private, no-store"  # never publicly cached
        assert "ETag" not in ok.headers


def test_hf_series_hours_and_validation(loaded: Engine) -> None:
    c = client(loaded)
    six = c.get("/api/v1/internal/stations/KDFW/hf?hours=6", headers=H).json()
    day = c.get("/api/v1/internal/stations/KDFW/hf?hours=24", headers=H).json()
    assert six["in_feed"] is True
    assert six["source"]["source"] == "5-minute ASOS data (NOAA MADIS)"
    assert "not official METAR" in six["source"]["attribution"]
    times = [x["observed_at"] for x in six["readings"]]
    assert times == sorted(times)
    assert len(six["readings"]) == 72  # 15:05 … 21:00 every 5 min (window is 6 h back from now)
    assert len(day["readings"]) == 181  # 06:00 … 21:00
    last = six["readings"][-1]
    assert last["temp"] == {
        "c": 20.0, "f_exact": 68.0, "f_rounded": 68, "f_possible": [68], "precision": "whole_c",
        "source": "hfmetar", "observed_at": "2026-11-27T21:00:00Z",
    }  # fmt: skip
    assert (last["wind_kt"], last["altim_inhg"], last["qc_temp"], last["revision"]) == (
        12, 30.07, "V", 0,
    )  # fmt: skip
    assert c.get("/api/v1/internal/stations/KDFW/hf?hours=5", headers=H).status_code == 422
    assert c.get("/api/v1/internal/stations/KZZZ/hf", headers=H).status_code == 404
    nyc = c.get("/api/v1/internal/stations/KNYC/hf", headers=H).json()
    assert (nyc["in_feed"], nyc["readings"]) == (False, [])


def test_hf_current_side_by_side_with_metar(loaded: Engine) -> None:
    body = client(loaded).get("/api/v1/internal/stations/KDFW/hf-current", headers=H).json()
    assert (body["status"], body["stale_after_minutes"], body["in_feed"]) == ("ok", 15, True)
    assert body["latest"]["observed_at"] == "2026-11-27T21:00:00Z"
    so = body["so_far"]
    assert so["high"]["value_c"] == 20.0  # the questioned 30 °C spike is left out …
    assert so["excluded_qc_count"] == 1  # … and counted
    assert so["missing_temp_count"] == 1
    assert so["low"]["value_c"] == 10.0
    assert so["low"]["observed_at"] == "2026-11-27T06:00:00Z"  # earliest of the ties
    assert so["low"]["temp"]["f_possible"] == [50]
    assert so["readings"] == 181
    m = body["metar"]
    assert m["latest"]["temp"]["f_exact"] == 62.96
    assert m["high_so_far"]["temp"]["f_rounded"] == 63
    assert m["low_so_far"]["value_c"] == 17.2
    assert body["climate_day"]["date"] == "2026-11-27"


def test_hf_current_stale_and_absent_stations(loaded: Engine) -> None:
    c = client(loaded)
    sea = c.get("/api/v1/internal/stations/KSEA/hf-current", headers=H).json()
    assert (sea["status"], sea["in_feed"]) == ("stale", True)
    nyc = c.get("/api/v1/internal/stations/KNYC/hf-current", headers=H).json()
    assert (nyc["status"], nyc["in_feed"], nyc["latest"]) == ("no_data", False, None)
    assert nyc["so_far"]["high"] is None


def test_map_covers_every_station(loaded: Engine) -> None:
    body = client(loaded).get("/api/v1/internal/map", headers=H).json()
    by = {x["station_id"]: x for x in body["stations"]}
    assert len(by) == len(load_registry())
    assert by["KDFW"]["status"] == "ok"
    assert by["KDFW"]["hf_so_far"]["high"]["value_c"] == 20.0
    assert by["KDFW"]["metar"]["latest"]["temp"]["c"] == 17.2
    assert by["KLAX"]["hf_latest"]["temp"]["f_possible"] == [60, 61]  # 16 °C
    assert by["KSEA"]["status"] == "stale"
    assert (by["KNYC"]["status"], by["KNYC"]["in_feed"]) == ("no_data", False)
    assert "lat" in by["KDFW"]  # filled by station enrichment, not by the seed


def test_status_hfmetar_block_and_public_strip_unchanged(loaded: Engine) -> None:
    body = client(loaded).get("/api/v1/status").json()
    assert "hfmetar" not in {x["key"] for x in body["sources"]}  # strip and web health unchanged
    hf = body["hfmetar"]
    assert hf["last_file"]["name"] == "hfmetar.20261127_2000.gz"
    assert hf["last_reading_at"] == "2026-11-27T21:00:00Z"
    assert hf["stations_reporting_30m"] == ["KDFW", "KLAX"]
    assert "KNYC" in hf["stations_missing_30m"]
    lat = hf["latency"]
    assert lat["received"]["p50_s"] == 142.0
    assert lat["rows"] > 0
    assert lat["fetched"]["count"] + lat["excluded_late"] == lat["rows"]
    assert hf["rounding_check"]["pairs"] == 0  # no METAR at a 5-minute mark here
