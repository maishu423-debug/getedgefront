"""GET /stations/{id}/models on runs ingested from the real text fixtures (no network)."""

from __future__ import annotations

import glob
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from edgefront_api.main import create_app
from edgefront_core.db import session_scope
from edgefront_core.metar_ingest import store_reports
from edgefront_core.model_text_ingest import PfmIngest, TextModelIngest, nomads_url
from edgefront_core.models import Station
from edgefront_core.nws_products import NwsProductLister
from edgefront_core.registry import load_registry
from edgefront_core.seed import seed
from edgefront_core.settings import Settings

REPO = Path(__file__).resolve().parents[3]
FIX = REPO / "packages" / "core" / "tests" / "fixtures"
NOW = datetime(2026, 11, 25, 14, 50, tzinfo=UTC)  # 08:50 CST
CFG = Settings(_env_file=None, app_env="test")
TEXT = {
    ("nbh", datetime(2026, 11, 25, 13, tzinfo=UTC)): "nbh_2026112513.txt",
    ("nbs", datetime(2026, 11, 25, 13, tzinfo=UTC)): "nbs_2026112513.txt",
    ("mav", datetime(2026, 11, 25, 6, tzinfo=UTC)): "mav_2026112506.txt",
    ("lav", datetime(2026, 11, 25, 13, 30, tzinfo=UTC)): "lav_202611251330.txt",
    ("lavx", datetime(2026, 11, 25, 13, 30, tzinfo=UTC)): "lavx_202611251330.txt",
}


def nosleep(_s: float) -> None:
    return None


def _nomads() -> httpx.Client:
    files = {nomads_url(p, c): FIX / "nomads_text" / f for (p, c), f in TEXT.items()}

    def handler(req: httpx.Request) -> httpx.Response:
        path = files.get(str(req.url))
        if path is None:
            return httpx.Response(404)
        return httpx.Response(200, content=b"" if req.method == "HEAD" else path.read_bytes())

    return httpx.Client(transport=httpx.MockTransport(handler))


def _nws() -> httpx.Client:
    docs: dict[str, list[dict[str, Any]]] = {}
    for p in glob.glob(str(FIX / "nws_pfm" / "PFM*.json")):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        docs.setdefault(Path(p).name[3:6], []).append(d)

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path.startswith("/products/types/PFM/locations/"):
            office = path.rsplit("/", 1)[1]
            graph = [
                {"id": d["id"], "issuanceTime": d["issuanceTime"], "issuingOffice": office}
                for d in sorted(docs.get(office, []), key=lambda d: d["issuanceTime"])[::-1]
            ]
            return httpx.Response(200, json={"@graph": graph})
        pid = path.rsplit("/", 1)[1]
        for ds in docs.values():
            for d in ds:
                if d["id"] == pid:
                    return httpx.Response(200, json=d)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def loaded(engine: Engine, session_factory: sessionmaker[Session]) -> Engine:
    with session_scope(session_factory) as s:
        seed(s, load_registry(REPO / "data" / "stations.yaml"))
        for sid, lat, lon, off in [
            ("KDFW", 32.89743, -97.02196, "FWD"),
            ("KMIA", 25.7881, -80.3169, "MFL"),
            ("KNYC", 40.78333, -73.96667, "OKX"),
        ]:
            st = s.get(Station, sid)
            assert st is not None
            st.lat, st.lon, st.nws_office = lat, lon, off
    ingest = TextModelIngest(_nomads(), sleep=nosleep)
    for model in ("nbm", "gfs_mos", "lamp"):
        assert ingest.run(session_factory, model, NOW).status == "complete"
    PfmIngest(NwsProductLister(_nws(), sleep=nosleep)).run(session_factory, NOW)
    return engine


def get(engine: Engine, url: str, now: datetime = NOW) -> dict[str, Any]:
    r = TestClient(create_app(engine, now=lambda: now, settings=CFG)).get(url)
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def by_id(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {m["id"]: m for m in body["models"]}


def z(d: int, h: int, mi: int = 0) -> str:
    return datetime(2026, 11, d, h, mi, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def test_kdfw_temp_today(loaded: Engine) -> None:
    body = get(loaded, "/api/v1/stations/KDFW/models?var=temp&span=today")
    assert body["unit"] == "degF"
    w = body["window"]
    assert (w["start"], w["end"], w["climate_date"]) == (z(25, 6), z(26, 6), "2026-11-25")
    assert w["start_local"] == "2026-11-25T00:00:00-06:00"
    m = by_id(body)
    assert list(m) == ["ifs", "gfs", "aifs", "gfs_mos", "nbm", "lamp", "pfm"]
    for gid in ("ifs", "gfs", "aifs"):
        assert m[gid]["available"] is False
        assert m[gid]["reason_code"] == "no_run"
    nbm = m["nbm"]
    assert nbm["available"] is True
    assert nbm["kind"] == "continuous"
    assert nbm["native_unit"] == "degF"
    assert (nbm["group"], nbm["label"]) == ("statistical", "NBM")
    assert nbm["run"]["cycle_time"] == z(25, 13)
    assert nbm["run"]["status"] == "complete"
    assert nbm["run"]["available_at"] == z(25, 14, 50)
    assert nbm["run"]["stale"] is False
    assert nbm["points"][0] == {
        "valid_time": z(25, 14), "value": 36.0, "category": None, "category_range": None,
        "is_computed": False,
    }  # fmt: skip
    assert all(z(25, 6) <= p["valid_time"] <= z(26, 6) for p in nbm["points"])
    assert len(nbm["points"]) == 17  # 14Z..06Z hourly
    assert m["gfs_mos"]["points"][0] == {
        "valid_time": z(25, 12), "value": 36.0, "category": None, "category_range": None,
        "is_computed": False,
    }  # fmt: skip
    assert m["lamp"]["run"]["cycle_time"] == z(25, 13, 30)
    pfm = m["pfm"]
    assert pfm["available"] is True
    assert pfm["run"]["issuer"] == "FWD"
    assert pfm["run"]["cycle_time"] == "2026-11-25T11:07:00Z"  # newest FWD fixture
    assert pfm["grid"]["point_name"] == "DFW Airport-Dallas TX"
    assert pfm["grid"]["distance_km"] < 3
    assert body["models"][0]["licence"] == "CC BY 4.0"


def test_48h_window_and_nbs_tail(loaded: Engine) -> None:
    body = get(loaded, "/api/v1/stations/KDFW/models?var=temp&span=48h")
    assert body["window"]["end"] == z(27, 6)
    pts = by_id(body)["nbm"]["points"]
    times = [p["valid_time"] for p in pts]
    assert z(26, 14) in times  # last NBH hour, then NBS every 3 h
    assert [t for t in times if t > z(26, 14)] == [
        z(26, 15), z(26, 18), z(26, 21), z(27, 0), z(27, 3), z(27, 6),
    ]  # fmt: skip


def test_categorical_cloud_and_rh(loaded: Engine) -> None:
    cloud = by_id(get(loaded, "/api/v1/stations/KMIA/models?var=cloud&span=today"))
    assert cloud["gfs_mos"]["kind"] == "categorical"
    assert cloud["gfs_mos"]["points"][0]["category"] == "OV"
    assert cloud["gfs_mos"]["points"][0]["value"] == 100.0  # §6.5 OVC midpoint
    assert cloud["nbm"]["kind"] == "continuous"
    pfm = by_id(get(loaded, "/api/v1/stations/KDFW/models?var=cloud&span=48h"))["pfm"]
    assert pfm["kind"] == "categorical"
    seen = {p["category"]: (p["value"], p["category_range"]) for p in pfm["points"]}
    # PFM codes plot at the midpoint of the PFM's own ranges (spec Table 2), not §6.5
    assert seen["CL"] == (2.5, "0% to ≤ 5%")
    if "FW" in seen:
        assert seen["FW"] == (15.0, "> 5% and ≤ 25%")
    assert cloud["gfs_mos"]["points"][0]["category_range"] is None
    assert cloud["nbm"]["native_unit"] == "pct"
    rh = by_id(get(loaded, "/api/v1/stations/KDFW/models?var=rh&span=today"))
    assert rh["nbm"]["points"][0]["is_computed"] is True
    assert rh["pfm"]["points"][0]["is_computed"] is False  # PFM prints its own RH
    assert rh["pfm"]["points"][0]["value"] == 92.0


def test_wind_from_pfm_mph_is_shown_in_kt(loaded: Engine) -> None:
    pfm = by_id(get(loaded, "/api/v1/stations/KDFW/models?var=wind&span=today"))["pfm"]
    assert pfm["native_unit"] == "mph"
    assert pfm["points"][0]["value"] == 9.0  # 10 mph = 8.69 kt → whole kt


def test_not_available_reasons(loaded: Engine) -> None:
    kmia = by_id(get(loaded, "/api/v1/stations/KMIA/models?var=temp&span=today"))
    assert kmia["pfm"]["available"] is False
    assert kmia["pfm"]["reason_code"] == "no_station"
    assert "no PFM point" in kmia["pfm"]["reason"]
    assert kmia["pfm"]["points"] == []
    khou = by_id(get(loaded, "/api/v1/stations/KHOU/models?var=temp&span=today"))
    assert khou["pfm"]["available"] is False
    # KNYC's office OKX has fixtures; the station is OK
    assert by_id(get(loaded, "/api/v1/stations/KNYC/models?var=temp"))["pfm"]["available"]


def test_stale_runs_and_validation(loaded: Engine) -> None:
    later = NOW + timedelta(hours=3)
    m = by_id(get(loaded, "/api/v1/stations/KDFW/models?var=temp&span=today", later))
    assert m["nbm"]["run"]["stale"] is True  # hourly model, nothing new for 3 h
    assert m["gfs_mos"]["run"]["stale"] is False  # 6-hourly model
    c = TestClient(create_app(loaded, now=lambda: NOW, settings=CFG))
    assert c.get("/api/v1/stations/KDFW/models?var=pressure").status_code == 422
    assert c.get("/api/v1/stations/KDFW/models?span=week").status_code == 422
    assert c.get("/api/v1/stations/KZZZ/models").status_code == 404


def test_observed_overlay(engine: Engine, session_factory: sessionmaker[Session]) -> None:
    obs_now = datetime(2026, 11, 24, 16, 30, tzinfo=UTC)
    with session_scope(session_factory) as s:
        seed(s, load_registry(REPO / "data" / "stations.yaml"))
        corpus: list[dict[str, Any]] = []
        for p in sorted(glob.glob(str(FIX / "aviationweather" / "metar_36h_batch*.json"))):
            corpus += json.loads(Path(p).read_text(encoding="utf-8"))
        store_reports(s, corpus, obs_now - timedelta(minutes=20))
    body = get(engine, "/api/v1/stations/KDFW/models?var=temp&span=today", obs_now)
    pts = body["observed"]["points"]
    assert pts
    assert all(body["window"]["start"] <= p["valid_time"] <= z(24, 16, 30) for p in pts)
    assert all(float(p["value"]).is_integer() for p in pts)  # whole °F
    cloud = get(engine, "/api/v1/stations/KDFW/models?var=cloud", obs_now)["observed"]["points"]
    assert {p["category"] for p in cloud} <= {"CLR", "FEW", "SCT", "BKN", "OVC", "VV"}
    assert all(m["reason_code"] == "no_run" for m in body["models"] if m["id"] != "pfm")
