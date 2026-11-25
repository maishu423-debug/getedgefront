"""Text-model ingest (NBM, GFS-MOS, LAMP, PFM) against the real fixtures, no network."""

from __future__ import annotations

import itertools
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from core_fixtures import FIXTURES
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.model_store import apply_retention, to_canonical, upsert_run
from edgefront_core.model_text_ingest import (
    PfmIngest,
    TextModelIngest,
    candidate_cycles,
    nomads_url,
)
from edgefront_core.models import ModelRun, ModelRunStation, ModelValue, SourceHealth, Station
from edgefront_core.nws_products import NwsProductLister
from edgefront_core.timeutil import as_utc

TEXT = FIXTURES / "nomads_text"
PFM = FIXTURES / "nws_pfm"


def nosleep(_s: float) -> None:
    return None


def _stations(factory: sessionmaker[Session]) -> None:
    with session_scope(factory) as s:
        for sid, off, point, lat, lon in [
            ("KDFW", "FWD", "DFW Airport-Dallas TX", 32.8998, -97.0403),
            ("KDAL", "FWD", "Dallas Love Field-Dallas TX", 32.8471, -96.8518),
            ("KMIA", "MFL", None, 25.7881, -80.3169),
            ("KZZZ", None, None, None, None),  # not in any bulletin
        ]:
            s.add(
                Station(
                    id=sid, name=sid, city="x", state="XX", tz="America/Chicago",
                    nws_office=off, pfm_point=point, lat=lat, lon=lon,
                )
            )  # fmt: skip


class FakeNomads:
    """Serves fixture bulletins at their real NOMADS URLs; everything else is 404."""

    def __init__(self, files: dict[str, str]) -> None:
        self.files = {nomads_url(k, _cycle(v)): (TEXT / f"{k}_{v}.txt") for k, v in files.items()}
        self.gets: list[str] = []
        self.heads: list[str] = []

    def handler(self, req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        path = self.files.get(url)
        if req.method == "HEAD":
            self.heads.append(url)
            return httpx.Response(200 if path else 404)
        self.gets.append(url)
        if path is None:
            return httpx.Response(404)
        return httpx.Response(200, content=path.read_bytes())


def _cycle(s: str) -> datetime:
    return datetime.strptime(s, "%Y%m%d%H%M" if len(s) == 12 else "%Y%m%d%H").replace(tzinfo=UTC)


def _client(fake: FakeNomads) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(fake.handler))


def _values(factory: sessionmaker[Session], model: str, sid: str, var: str) -> list[ModelValue]:
    with session_scope(factory) as s:
        return list(
            s.execute(
                select(ModelValue)
                .join(ModelRun, ModelRun.id == ModelValue.run_id)
                .where(
                    ModelRun.model == model,
                    ModelValue.station_id == sid,
                    ModelValue.variable == var,
                )
                .order_by(ModelValue.valid_time)
            ).scalars()
        )


def test_candidate_cycles() -> None:
    now = datetime(2026, 11, 25, 14, 20, tzinfo=UTC)
    assert candidate_cycles("nbm", now)[:2] == [
        now.replace(minute=0),
        now.replace(hour=13, minute=0),
    ]
    assert candidate_cycles("lamp", now)[0] == now.replace(hour=13, minute=30)
    assert candidate_cycles("gfs_mos", now)[:2] == [
        now.replace(hour=12, minute=0),
        now.replace(hour=6, minute=0),
    ]


def test_units_to_canonical() -> None:
    assert to_canonical(32.0, "degF") == (0.0, "degC")
    v, u = to_canonical(23.0, "mph")
    assert u == "kt"
    assert v == pytest.approx(19.99, abs=0.01)
    assert to_canonical(None, "category") == (None, "category")
    with pytest.raises(ValueError, match="unknown native unit"):
        to_canonical(1.0, "furlongs")


def test_nbm_merges_nbh_then_nbs_and_marks_missing_stations(
    session_factory: sessionmaker[Session],
) -> None:
    _stations(session_factory)
    fake = FakeNomads({"nbh": "2026112513", "nbs": "2026112513"})
    now = datetime(2026, 11, 25, 14, 20, tzinfo=UTC)
    summ = TextModelIngest(_client(fake), sleep=nosleep).run(session_factory, "nbm", now)
    assert summ.status == "complete"
    assert summ.cycle == datetime(2026, 11, 25, 13, tzinfo=UTC)
    assert summ.files == ["nbh", "nbs"]
    assert sorted(summ.stations_missing) == ["KZZZ"]

    temps = _values(session_factory, "nbm", "KDFW", "temp")
    assert as_utc(temps[0].valid_time) == datetime(2026, 11, 25, 14, tzinfo=UTC)
    assert (temps[0].native_value, temps[0].native_unit, temps[0].unit) == (36.0, "degF", "degC")
    assert temps[0].value == pytest.approx(2.2222, abs=1e-3)
    steps = [(b.valid_time - a.valid_time) for a, b in itertools.pairwise(temps)]
    assert set(steps[:24]) == {timedelta(hours=1)}  # NBH hourly to +25 h
    assert set(steps[25:]) == {timedelta(hours=3)}  # then NBS 3-hourly
    rh = _values(session_factory, "nbm", "KDFW", "rh")
    assert rh
    assert all(r.is_computed for r in rh)
    cloud = _values(session_factory, "nbm", "KDFW", "cloud")
    assert (cloud[0].unit, cloud[0].category) == ("pct", None)

    with session_scope(session_factory) as s:
        rs = {r.station_id: r for r in s.execute(select(ModelRunStation)).scalars()}
        assert rs["KZZZ"].status == "not_available"
        assert rs["KZZZ"].reason == "Not in the NBM station bulletin"
        run = s.execute(select(ModelRun)).scalar_one()
        assert (run.status, run.steps_fetched, run.steps_expected) == ("complete", 2, 2)
        assert as_utc(run.available_at) == now
        health = s.get(SourceHealth, "model_nbm")
        assert health is not None
        assert health.last_item_time == run.cycle_time

    # Second poll: newest cycle complete -> no download at all.
    fake.gets.clear()
    again = TextModelIngest(_client(fake), sleep=nosleep).run(session_factory, "nbm", now)
    assert again.status == "up_to_date"
    assert fake.gets == []


def test_nbm_partial_until_nbs_arrives(session_factory: sessionmaker[Session]) -> None:
    _stations(session_factory)
    now = datetime(2026, 11, 25, 13, 40, tzinfo=UTC)
    fake = FakeNomads({"nbh": "2026112513"})
    first = TextModelIngest(_client(fake), sleep=nosleep).run(session_factory, "nbm", now)
    assert first.status == "partial"
    fake.gets.clear()
    second = TextModelIngest(_client(fake), sleep=nosleep).run(session_factory, "nbm", now)
    assert second.status == "partial"
    assert fake.gets == []  # NBS still absent: the 28 MB NBH is not downloaded again
    fake2 = FakeNomads({"nbh": "2026112513", "nbs": "2026112513"})
    later = now + timedelta(minutes=15)
    third = TextModelIngest(_client(fake2), sleep=nosleep).run(session_factory, "nbm", later)
    assert third.status == "complete"
    with session_scope(session_factory) as s:
        run = s.execute(select(ModelRun)).scalar_one()
        assert as_utc(run.available_at) == now  # first seen, not last updated
        assert run.status == "complete"


@pytest.mark.parametrize(
    ("model", "files", "now", "cycle", "first_valid", "temp_f", "cloud"),
    [
        ("gfs_mos", {"mav": "2026112506"}, (14, 50), (6, 0), (12, 0), 36.0, "CL"),
        ("lamp", {"lav": "202611251330"}, (14, 50), (13, 30), (14, 0), 35.0, "CL"),
    ],
)
def test_mav_and_lav(
    session_factory: sessionmaker[Session],
    model: str,
    files: dict[str, str],
    now: tuple[int, int],
    cycle: tuple[int, int],
    first_valid: tuple[int, int],
    temp_f: float,
    cloud: str,
) -> None:
    _stations(session_factory)
    fake = FakeNomads(files)
    t = datetime(2026, 11, 25, *now, tzinfo=UTC)
    summ = TextModelIngest(_client(fake), sleep=nosleep).run(session_factory, model, t)
    assert summ.status == "complete"
    assert summ.cycle == datetime(2026, 11, 25, *cycle, tzinfo=UTC)
    temps = _values(session_factory, model, "KDFW", "temp")
    assert as_utc(temps[0].valid_time) == datetime(2026, 11, 25, *first_valid, tzinfo=UTC)
    assert temps[0].native_value == temp_f
    c = _values(session_factory, model, "KDFW", "cloud")[0]
    assert (c.value, c.unit, c.category) == (None, "category", cloud)
    assert _values(session_factory, model, "KMIA", "temp")  # MIA is in MOS/LAMP
    assert _values(session_factory, model, "KZZZ", "temp") == []


def test_upstream_error_is_recorded(session_factory: sessionmaker[Session]) -> None:
    _stations(session_factory)

    def boom(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(boom))
    with pytest.raises(httpx.HTTPError):
        TextModelIngest(client, sleep=nosleep).run(session_factory, "lamp")
    with session_scope(session_factory) as s:
        h = s.get(SourceHealth, "model_lamp")
        assert h is not None
        assert h.last_error
        assert h.last_success_at is None


def test_retention_keeps_four_runs_per_issuer(session_factory: sessionmaker[Session]) -> None:
    _stations(session_factory)
    base = datetime(2026, 11, 25, tzinfo=UTC)
    with session_scope(session_factory) as s:
        for h in range(6):
            upsert_run(s, "lamp", base + timedelta(hours=h), now=base)
        for h in range(5):
            upsert_run(s, "pfm", base + timedelta(hours=h), now=base, issuer="FWD")
        upsert_run(s, "pfm", base, now=base, issuer="OKX")
        assert apply_retention(s, "lamp") == 2
        assert apply_retention(s, "pfm") == 1
    with session_scope(session_factory) as s:
        rows = s.execute(select(ModelRun.model, ModelRun.issuer, func.count()).group_by(
            ModelRun.model, ModelRun.issuer
        )).all()  # fmt: skip
        assert sorted(rows) == [("lamp", "", 4), ("pfm", "FWD", 4), ("pfm", "OKX", 1)]
        newest = s.execute(
            select(func.min(ModelRun.cycle_time)).where(ModelRun.model == "lamp")
        ).scalar_one()
        assert as_utc(newest) == base + timedelta(hours=2)


# ---------------------------------------------------------------- PFM


class FakeNws:
    def __init__(self) -> None:
        self.docs = {}
        for name in ("PFMFWD_202611250806.json", "PFMFWD_202611251107.json"):
            doc = json.loads((PFM / name).read_text(encoding="utf-8"))
            self.docs[doc["id"]] = doc

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/products/types/PFM/locations/FWD":
            graph = [
                {"id": d["id"], "issuanceTime": d["issuanceTime"], "issuingOffice": "KFWD"}
                for d in sorted(self.docs.values(), key=lambda d: d["issuanceTime"], reverse=True)
            ]
            return httpx.Response(200, json={"@graph": graph})
        pid = path.rsplit("/", 1)[-1]
        if path.startswith("/products/") and pid in self.docs:
            return httpx.Response(200, json=self.docs[pid])
        return httpx.Response(404)


def test_pfm_ingest_two_issuances(session_factory: sessionmaker[Session]) -> None:
    _stations(session_factory)
    fake = FakeNws()
    lister = NwsProductLister(
        httpx.Client(transport=httpx.MockTransport(fake.handler)), sleep=nosleep
    )
    now = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
    summ = PfmIngest(lister).run(session_factory, now)
    assert summ.offices == 1
    assert summ.new_products == 2
    assert summ.stations_ok == 4
    assert summ.stations_failed == {}
    with session_scope(session_factory) as s:
        runs = s.execute(select(ModelRun).order_by(ModelRun.cycle_time)).scalars().all()
        assert [(r.issuer, r.status) for r in runs] == [("FWD", "complete"), ("FWD", "complete")]
        assert as_utc(runs[-1].cycle_time) == datetime(2026, 11, 25, 11, 7, tzinfo=UTC)
        rs = s.get(ModelRunStation, (runs[-1].id, "KDFW"))
        assert rs is not None
        assert rs.point_name == "DFW Airport-Dallas TX"
        assert (rs.grid_lat, rs.grid_lon) == (32.91, -97.03)
        assert rs.grid_distance_km is not None
        assert rs.grid_distance_km < 3
        # KMIA has no PFM point: no row at all (the API explains it from the registry)
        assert s.get(ModelRunStation, (runs[-1].id, "KMIA")) is None
    wind = list(_values(session_factory, "pfm", "KDFW", "wind"))
    newest = max(v.run_id for v in wind)
    w0 = next(v for v in wind if v.run_id == newest)
    assert (w0.native_value, w0.native_unit, w0.unit) == (10.0, "mph", "kt")
    assert w0.value == pytest.approx(8.69, abs=0.01)
    rh = [v for v in _values(session_factory, "pfm", "KDFW", "rh") if v.run_id == newest]
    assert rh[0].value == 92.0
    assert not any(v.is_computed for v in rh)  # the product's own RH

    # Nothing new on the next poll
    again = PfmIngest(lister).run(session_factory, now + timedelta(minutes=15))
    assert again.new_products == 0
