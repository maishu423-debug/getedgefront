"""GFS / IFS / AIFS: decoding, nearest land point, index parsing and the ingest, on the cropped
real fixtures in tests/fixtures/grib (see its README). No network."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.models import ModelRun, ModelRunStation, ModelValue, SourceHealth, Station
from edgefront_core.timeutil import as_utc
from edgefront_worker.grib.fields import (
    Field,
    GribError,
    decode,
    height_m,
    km_between,
    nearest_land_point,
)
from edgefront_worker.grib.ingest import GribModel, GribModelIngest, candidate_cycles
from edgefront_worker.grib.sources import (
    GFS_AWS,
    GFS_NOMADS,
    ecmwf_url,
    gfs_patterns,
    gfs_url,
    parse_ecmwf_index,
    parse_wgrib_idx,
)

FIX = Path(__file__).parent / "fixtures" / "grib"
CYCLE = datetime(2026, 11, 25, 6, tzinfo=UTC)
NOW = datetime(2026, 11, 25, 15, 30, tzinfo=UTC)
# NWS /stations positions (as enriched in the database)
STATIONS = {
    "KDFW": (32.8998, -97.0403),
    "KSFO": (37.6196, -122.3656),  # bay shore
    "KMIA": (25.7881, -80.3169),
    "KBOS": (42.3606, -71.0097),  # harbour
    "KSEA": (47.4447, -122.3144),
    "KDEN": (39.8466, -104.6562),
}


def nosleep(_s: float) -> None:
    return None


def messages(name: str) -> dict[str, Field]:
    """All messages of a fixture step file, keyed by shortName."""
    data = (FIX / f"{name}.grib2").read_bytes()
    out: dict[str, Field] = {}
    pos = 0
    while (k := data.find(b"GRIB", pos)) >= 0:
        length = int.from_bytes(data[k + 8 : k + 16], "big")  # GRIB2 section 0 total length
        f = decode(data[k : k + length])
        out[f.short_name] = f
        pos = k + length
    return out


# ---------------------------------------------------------------- decoding / space


def test_decode_cropped_fields_and_units() -> None:
    gfs = messages("gfs_2026112506_f000")
    assert set(gfs) == {"2t", "2d", "2r", "10u", "10v", "tcc", "lsm", "orog"}
    t = gfs["2t"]
    assert (t.units, t.data_date, t.data_time, t.step) == ("K", 20261125, 600, "0")
    assert t.values.shape == (105, 237)
    ifs = messages("ifs_2026112506_0h")
    assert ifs["tcc"].units == "(0 - 1)"  # IFS cloud is a fraction ...
    aifs = messages("aifs_2026112506_0h")
    assert aifs["tcc"].units == "%"  # ... AIFS cloud is percent (units key decides)
    assert ifs["z"].units.startswith("m**2")


@pytest.mark.parametrize(
    "model", ["gfs_2026112506_f000", "ifs_2026112506_0h", "aifs_2026112506_0h"]
)
def test_every_station_gets_a_nearby_land_point(model: str) -> None:
    f = messages(model)
    lsm = f["lsm"]
    for sid, (lat, lon) in STATIONS.items():
        p = nearest_land_point(lsm, lat, lon)
        assert p.is_land, sid
        assert p.land_fraction >= 0.5
        assert p.distance_km < 25, (sid, p.distance_km)  # 0.25° grid: < ~20 km
        assert km_between(lat, lon, p.lat, p.lon) == pytest.approx(p.distance_km)


def test_land_point_skips_a_nearer_sea_point() -> None:
    lsm = messages("ifs_2026112506_0h")["lsm"]
    lat, lon = STATIONS["KDFW"]
    j, i = lsm.grid.nearest_ij(lat, lon)
    wet = Field(lsm.short_name, lsm.units, 0, 0, "0", lsm.grid, lsm.values.copy())
    wet.values[j, i] = 0.2  # pretend the nearest point is water
    p = nearest_land_point(wet, lat, lon)
    assert (p.j, p.i) != (j, i)
    assert p.is_land
    nearest = nearest_land_point(lsm, lat, lon)
    assert p.distance_km > nearest.distance_km


def test_heights_from_orography() -> None:
    lat, lon = STATIONS["KDEN"]
    gfs = messages("gfs_2026112506_f000")
    ifs = messages("ifs_2026112506_0h")
    hg = height_m(gfs["orog"], nearest_land_point(gfs["lsm"], lat, lon))
    hi = height_m(ifs["z"], nearest_land_point(ifs["lsm"], lat, lon))
    assert hg is not None
    assert hi is not None
    assert 1500 < hg < 1800  # Denver ~1650 m; GFS HGT is in gpm
    assert 1500 < hi < 1800  # IFS z / g


def test_grid_seam_and_negative_longitudes() -> None:
    gfs = messages("gfs_2026112506_f000")["2t"].grid  # lon 235..294 (0..360 convention)
    ifs = messages("ifs_2026112506_0h")["2t"].grid
    for g in (gfs, ifs):
        j, i = g.nearest_ij(*STATIONS["KDFW"])
        assert g.contains(j, i)
        assert g.lon(i) == pytest.approx(-97.0, abs=0.13)
        assert g.lat(j) == pytest.approx(32.9, abs=0.13)
    with pytest.raises(GribError, match="outside"):
        nearest_land_point(messages("gfs_2026112506_f000")["lsm"], 10.0, 10.0)


# ---------------------------------------------------------------- indexes


def test_gfs_idx_patterns_pick_instantaneous_cloud() -> None:
    text = (FIX / "gfs_2026112506_f006.idx").read_text(encoding="utf-8")
    refs = parse_wgrib_idx(text, "u", gfs_patterns(6))
    assert set(refs) == {"temp", "dewpt", "rh", "u10", "v10", "cloud"}
    assert refs["temp"].offset == 0
    assert refs["cloud"].length is None  # last message: open-ended range
    assert refs["dewpt"].length == refs["rh"].offset - refs["dewpt"].offset
    assert gfs_patterns(6)["cloud"] == ":TCDC:entire atmosphere:6 hour fcst:"  # not "0-6 hour ave"
    assert "lsm" in gfs_patterns(0)
    assert "lsm" not in gfs_patterns(6)


def test_ecmwf_index_static_only_at_step_0() -> None:
    t0 = (FIX / "ifs_2026112506_0h.index").read_text(encoding="utf-8")
    assert set(parse_ecmwf_index(t0, "u", with_static=True)) == {
        "temp", "dewpt", "u10", "v10", "cloud", "lsm", "orog",
    }  # fmt: skip
    t3 = (FIX / "ifs_2026112506_3h.index").read_text(encoding="utf-8")
    assert set(parse_ecmwf_index(t3, "u", with_static=False)) == {
        "temp", "dewpt", "u10", "v10", "cloud",
    }  # fmt: skip


def test_urls() -> None:
    assert gfs_url(GFS_AWS, CYCLE, 6) == (
        "https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20261125/06/atmos/gfs.t06z.pgrb2.0p25.f006"
    )
    assert ecmwf_url("aifs-single", CYCLE, 6) == (
        "https://data.ecmwf.int/forecasts/20261125/06z/aifs-single/0p25/oper/"
        "20261125060000-6h-oper-fc.grib2"
    )
    assert candidate_cycles(NOW)[:2] == [
        datetime(2026, 11, 25, 12, tzinfo=UTC),
        datetime(2026, 11, 25, 6, tzinfo=UTC),
    ]


# ---------------------------------------------------------------- ingest


class FakeServer:
    """Serves the fixture step files at their real URLs, with Range support."""

    def __init__(self, files: dict[str, str]) -> None:
        self.files: dict[str, Path] = {}
        for url, name in files.items():
            self.files[url] = FIX / name
        self.ranges = 0

    def handler(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if url.endswith((".idx", ".index")):
            base = url.removesuffix(".idx") if url.endswith(".idx") else url.removesuffix(".index")
            for u, p in self.files.items():
                if u.removesuffix(".grib2") == base or u == base:
                    ext = ".idx" if url.endswith(".idx") else ".index"
                    return httpx.Response(200, text=p.with_suffix(ext).read_text("utf-8"))
            return httpx.Response(404)
        path = self.files.get(url)
        if path is None:
            return httpx.Response(404)
        data = path.read_bytes()
        rng = req.headers.get("Range", "")
        a, _, b = rng.removeprefix("bytes=").partition("-")
        self.ranges += 1
        return httpx.Response(206, content=data[int(a) : (int(b) + 1) if b else None])


def _stations(factory: sessionmaker[Session]) -> None:
    with session_scope(factory) as s:
        for sid, (lat, lon) in STATIONS.items():
            s.add(Station(id=sid, name=sid, city="x", state="XX", tz="UTC", lat=lat, lon=lon))


def _ingest(server: FakeServer, models: dict[str, GribModel]) -> GribModelIngest:
    return GribModelIngest(
        httpx.Client(transport=httpx.MockTransport(server.handler)), sleep=nosleep, models=models
    )


def _vals(factory: sessionmaker[Session], model: str, sid: str, var: str) -> list[ModelValue]:
    with session_scope(factory) as s:
        return list(
            s.execute(
                select(ModelValue)
                .join(ModelRun, ModelRun.id == ModelValue.run_id)
                .where(ModelRun.model == model, ModelValue.station_id == sid,
                       ModelValue.variable == var)
                .order_by(ModelValue.valid_time)
            ).scalars()
        )  # fmt: skip


def test_gfs_ingest_from_aws_then_nomads_fallback(session_factory: sessionmaker[Session]) -> None:
    _stations(session_factory)
    server = FakeServer(
        {
            gfs_url(GFS_AWS, CYCLE, 0): "gfs_2026112506_f000.grib2",
            gfs_url(GFS_NOMADS, CYCLE, 6): "gfs_2026112506_f006.grib2",  # not on AWS yet
        }
    )
    models = {"gfs": GribModel("gfs", (0, 6))}
    summ = _ingest(server, models).run(session_factory, "gfs", NOW)
    assert summ.status == "complete"
    assert summ.cycle == CYCLE
    assert summ.steps_new == [0, 6]
    assert summ.sources == {"aws": 1, "nomads": 1}

    t = _vals(session_factory, "gfs", "KDFW", "temp")
    assert [as_utc(v.valid_time).hour for v in t] == [6, 12]
    assert t[0].native_unit == "K"
    assert t[0].native_value is not None
    assert t[0].value == pytest.approx(t[0].native_value - 273.15)
    # same grid point as the README's KDFW check: cropped 278.2400 K at f000
    assert t[0].native_value == pytest.approx(278.24, abs=0.02)
    rh = _vals(session_factory, "gfs", "KDFW", "rh")
    assert not any(v.is_computed for v in rh)  # GFS has its own 2 m RH
    w = _vals(session_factory, "gfs", "KDFW", "wind")[0]
    assert w.native_unit == "m/s"
    assert w.native_value == pytest.approx(math.hypot(0.8805, -3.4827), abs=0.01)
    assert w.native_value is not None
    assert w.value == pytest.approx(w.native_value * 1.943844492, abs=1e-6)
    with session_scope(session_factory) as s:
        rs = s.get(ModelRunStation, (s.execute(select(ModelRun.id)).scalar_one(), "KDFW"))
        assert rs is not None
        assert rs.status == "ok"
        assert rs.grid_distance_km is not None
        assert rs.grid_distance_km < 20
        assert rs.land_fraction == 1.0
        assert rs.height_m == pytest.approx(172.7, abs=0.1)
        run = s.execute(select(ModelRun)).scalar_one()
        assert (run.status, run.steps_fetched, run.steps_expected) == ("complete", 2, 2)
        assert s.get(SourceHealth, "model_gfs") is not None

    # Up to date: no more transfers.
    server.ranges = 0
    again = _ingest(server, models).run(session_factory, "gfs", NOW)
    assert again.status == "up_to_date"
    assert server.ranges == 0


@pytest.mark.parametrize(("model", "od", "step"), [("ifs", "ifs", 3), ("aifs", "aifs-single", 6)])
def test_ecmwf_partial_then_complete(
    session_factory: sessionmaker[Session], model: str, od: str, step: int
) -> None:
    _stations(session_factory)
    models = {model: GribModel(model, (0, step), od)}
    only0 = FakeServer({ecmwf_url(od, CYCLE, 0): f"{model}_2026112506_0h.grib2"})
    first = _ingest(only0, models).run(session_factory, model, NOW)
    assert first.status == "partial"
    assert first.steps_new == [0]
    both = FakeServer(
        {
            ecmwf_url(od, CYCLE, 0): f"{model}_2026112506_0h.grib2",
            ecmwf_url(od, CYCLE, step): f"{model}_2026112506_{step}h.grib2",
        }
    )
    second = _ingest(both, models).run(session_factory, model, NOW)
    assert second.status == "complete"
    assert second.steps_new == [step]  # step 0 is not downloaded again
    temps = _vals(session_factory, model, "KDFW", "temp")
    assert [as_utc(v.valid_time).hour for v in temps] == [6, 6 + step]
    cloud = _vals(session_factory, model, "KDFW", "cloud")
    assert all(v.unit == "pct" and 0 <= (v.value or 0) <= 100 for v in cloud)
    assert cloud[0].native_unit == ("fraction" if model == "ifs" else "pct")
    rh = _vals(session_factory, model, "KDFW", "rh")
    assert rh
    assert all(v.is_computed for v in rh)  # ECMWF open data has no 2 m RH: computed


def test_wrong_cycle_in_message_is_rejected(session_factory: sessionmaker[Session]) -> None:
    _stations(session_factory)
    # Serve the 06Z files under the 12Z URLs: the message dates must not be trusted blindly.
    later = datetime(2026, 11, 25, 12, tzinfo=UTC)
    server = FakeServer({ecmwf_url("ifs", later, 0): "ifs_2026112506_0h.grib2"})
    with pytest.raises(GribError, match="message is for"):
        _ingest(server, {"ifs": GribModel("ifs", (0,), "ifs")}).run(
            session_factory, "ifs", datetime(2026, 11, 25, 17, tzinfo=UTC)
        )


def test_values_are_finite() -> None:
    for name in ("gfs_2026112506_f006", "ifs_2026112506_3h", "aifs_2026112506_6h"):
        for f in messages(name).values():
            assert np.isfinite(f.values).all(), (name, f.short_name)
