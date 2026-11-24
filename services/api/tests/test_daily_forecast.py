"""/daily-summaries, /forecast, board nws_today_high_f and /status, on real stored fixtures."""

from __future__ import annotations

import glob
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from edgefront_api.main import create_app
from edgefront_core.cli_ingest import cli_row
from edgefront_core.db import session_scope
from edgefront_core.dsm_ingest import dsm_row
from edgefront_core.models import NwsForecast, Station
from edgefront_core.nws_products import RawProduct
from edgefront_core.registry import load_registry
from edgefront_core.seed import seed
from edgefront_core.settings import Settings
from edgefront_core.source_health import record_success

REPO = Path(__file__).resolve().parents[3]
FIX = REPO / "packages" / "core" / "tests" / "fixtures"
NOW = datetime(2026, 11, 24, 17, 30, tzinfo=UTC)  # 11:30 CST / 12:30 EST
CFG = Settings(_env_file=None, app_env="test")


def _nws_raw(path: Path) -> RawProduct:
    d = json.loads(path.read_text(encoding="utf-8"))
    return RawProduct(
        d["id"], datetime.fromisoformat(d["issuanceTime"]), d["issuingOffice"], None,
        d["productText"], d["@id"],
    )  # fmt: skip


def _iem_raw(fname: str, pid: str) -> RawProduct:
    entered = datetime.strptime(pid[:12], "%Y%m%d%H%M").replace(tzinfo=UTC)
    text = (FIX / "iem_dsm" / fname).read_text(encoding="utf-8")
    return RawProduct(pid, entered, pid.split("-")[1], "CDUS27 " + pid.split("-")[1], text, "x")


@pytest.fixture
def loaded(engine: Engine, session_factory: sessionmaker[Session]) -> Engine:
    with session_scope(session_factory) as s:
        seed(s, load_registry(REPO / "data" / "stations.yaml"))
        # Positions/grid normally come from enrichment.
        for sid, lat, lon, off, x, y in [
            ("KDFW", 32.89743, -97.02196, "FWD", 81, 109),
            ("KNYC", 40.78333, -73.96667, "OKX", 34, 45),
        ]:
            st = s.get(Station, sid)
            assert st is not None
            st.lat, st.lon, st.nws_office, st.grid_x, st.grid_y = lat, lon, off, x, y
    with session_scope(session_factory) as s:
        stations = {st.id: st for st in s.query(Station)}
        for p in glob.glob(str(FIX / "nws_cli" / "CLI*.json")):
            loc = Path(p).name[3:6]
            s.add(cli_row(stations["K" + loc], _nws_raw(Path(p)), NOW))
        for p in glob.glob(str(FIX / "nws_dsm" / "DSMNYC_*.json")):
            s.add(dsm_row(stations["KNYC"], "nws_api", _nws_raw(Path(p)), NOW))
        readme = (FIX / "iem_dsm" / "README.md").read_text(encoding="utf-8")
        for fname, pid in re.findall(r"`(DSMDFW\w+\.txt)` \| \S+/nwstext/(\S+) \|", readme):
            s.add(dsm_row(stations["KDFW"], "iem", _iem_raw(fname, pid), NOW))
        for sid in ("KDFW", "KNYC"):
            fc = json.loads((FIX / "nws_forecast" / f"{sid}_forecast.json").read_text("utf-8"))
            hr = json.loads(
                (FIX / "nws_forecast" / f"{sid}_forecast_hourly.json").read_text("utf-8")
            )
            s.add(
                NwsForecast(
                    station_id=sid, office=stations[sid].nws_office or "",
                    update_time=datetime.fromisoformat(fc["properties"]["updateTime"]),
                    periods=fc["properties"]["periods"], hourly=hr["properties"]["periods"][:48],
                    source="api.weather.gov/gridpoints", fetched_at=NOW - timedelta(minutes=5),
                )
            )  # fmt: skip
        for key in ("cli", "dsm_iem", "dsm_nws", "forecast", "metar", "worker"):
            record_success(s, key, NOW - timedelta(minutes=2))
    return engine


def client(engine: Engine, now: datetime = NOW) -> TestClient:
    return TestClient(create_app(engine, now=lambda: now, settings=CFG))


def rows(body: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(r["product"], r["day"]): r for r in body["rows"]}


def test_daily_summaries_kdfw(loaded: Engine) -> None:
    body = client(loaded).get("/api/v1/stations/KDFW/daily-summaries").json()
    assert (body["status"], body["today"], body["yesterday"], body["times_are"]) == (
        "ok", "2026-11-24", "2026-11-23", "LST",
    )  # fmt: skip
    r = rows(body)
    assert [(x["product"], x["day"]) for x in body["rows"]] == [
        ("CLI", "today"), ("DSM", "today"), ("CLI", "yesterday"), ("DSM", "yesterday"),
    ]  # fmt: skip
    cli_t = r[("CLI", "today")]
    assert cli_t["status"] == "not_issued_yet"
    assert "No CLI for today yet" in cli_t["reason"]
    cli_y = r[("CLI", "yesterday")]
    assert cli_y["status"] == "ok"
    assert cli_y["covers"] == {"date": "2026-11-23", "kind": "final"}
    assert (cli_y["issuer"], cli_y["max_f"], cli_y["max_time_local"]) == ("KFWD", 57, "14:07")
    assert (cli_y["normal_high_f"], cli_y["normal_low_f"]) == (64, 44)
    assert cli_y["issuances_for_day"] == 3  # two intraday + the final
    assert cli_y["raw_text"].startswith("\n000")
    dsm_y = r[("DSM", "yesterday")]
    assert dsm_y["status"] == "ok"
    assert dsm_y["source"] == "iem"
    assert dsm_y["attribution"] == "DSM via Iowa Environmental Mesonet, Iowa State University"
    # No final for the 23rd in the fixtures → the latest intraday (DS 1800) is shown as so_far.
    assert dsm_y["covers"] == {"date": "2026-11-23", "kind": "so_far"}
    assert dsm_y["valid_as_of_local"] == "18:00"
    assert dsm_y["peak_gust"] == {"dir_deg": 10, "speed_mph": 30, "time_local": "07:44"}
    assert dsm_y["normal_high_f"] is None
    assert r[("DSM", "today")]["status"] == "not_issued_yet"
    assert {x["source"] for x in body["sources"]} == {
        "api.weather.gov/products (CLI)",
        "mesonet.agron.iastate.edu AFOS archive (DSM)",
    }


def test_daily_summaries_knyc_nws_dsm(loaded: Engine) -> None:
    r = rows(client(loaded).get("/api/v1/stations/KNYC/daily-summaries").json())
    dsm_y = r[("DSM", "yesterday")]
    assert (dsm_y["status"], dsm_y["source"], dsm_y["attribution"]) == ("ok", "nws_api", None)
    assert dsm_y["covers"]["kind"] == "final"
    cli_y = r[("CLI", "yesterday")]
    assert (cli_y["max_f"], cli_y["min_f"], cli_y["covers"]["kind"]) == (69, 50, "final")


def test_correction_supersedes(loaded: Engine) -> None:
    r = rows(client(loaded).get("/api/v1/stations/KOKC/daily-summaries").json())
    cli_y = r[("CLI", "yesterday")]
    assert cli_y["is_correction"] is True
    assert cli_y["issuances_for_day"] == 2


def test_no_daily_summary_for_kbkf_and_cli_missing_for_kdal(loaded: Engine) -> None:
    bkf = client(loaded).get("/api/v1/stations/KBKF/daily-summaries").json()
    assert bkf["status"] == "none_available"
    assert bkf["message"] == "No daily summary available for this station"
    assert all(x["status"] == "not_available" for x in bkf["rows"])
    dal = rows(client(loaded).get("/api/v1/stations/KDAL/daily-summaries").json())
    assert dal[("CLI", "today")]["status"] == "not_available"
    assert dal[("CLI", "today")]["reason"] == "Not published for this station"
    assert dal[("DSM", "today")]["status"] == "not_issued_yet"


def test_forecast_kdfw_morning(loaded: Engine) -> None:
    body = client(loaded).get("/api/v1/stations/KDFW/forecast").json()
    assert (body["status"], body["label"], body["office"]) == ("ok", "FORECAST · NWS", "FWD")
    assert (body["today_high_f"], body["tonight_low_f"]) == (50, 35)
    assert body["today"]["name"] == "Today"
    assert body["today"]["detailed"]
    assert len(body["hourly"]) == 7
    assert body["update_time"] == "2026-11-24T17:06:44Z"
    assert body["weather_gov_url"].startswith(
        "https://forecast.weather.gov/MapClick.php?lat=32.8974"
    )


def test_forecast_evening_today_high_is_null(loaded: Engine) -> None:
    evening = datetime(2026, 11, 25, 1, 0, tzinfo=UTC)  # 19:00 CST
    body = client(loaded, evening).get("/api/v1/stations/KDFW/forecast").json()
    assert body["today_high_f"] is None
    assert "ended" in body["today_note"]
    assert body["tonight_low_f"] == 35
    assert body["status"] == "stale"  # fetched > 3 x 30 min before this "now"


def test_forecast_no_data(loaded: Engine) -> None:
    body = client(loaded).get("/api/v1/stations/KMIA/forecast").json()
    assert body["status"] == "no_data"
    assert body["today_high_f"] is None
    assert body["hourly"] == []


def test_board_has_nws_today_high(loaded: Engine) -> None:
    rows_ = {r["id"]: r for r in client(loaded).get("/api/v1/stations").json()["stations"]}
    assert rows_["KDFW"]["nws_today_high_f"] == 50
    assert rows_["KMIA"]["nws_today_high_f"] is None


def test_status_lists_new_sources(loaded: Engine) -> None:
    keys = {x["key"]: x for x in client(loaded).get("/api/v1/status").json()["sources"]}
    assert {"cli", "dsm_nws", "dsm_iem", "forecast", "metar", "worker"} <= set(keys)
    assert keys["dsm_iem"]["schedule_seconds"] == 720
    assert all(keys[k]["healthy"] for k in ("cli", "dsm_iem", "dsm_nws", "forecast"))


def test_unknown_station_404(loaded: Engine) -> None:
    assert client(loaded).get("/api/v1/stations/KZZZ/daily-summaries").status_code == 404
    assert client(loaded).get("/api/v1/stations/KZZZ/forecast").status_code == 404
