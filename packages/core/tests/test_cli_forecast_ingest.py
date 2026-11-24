"""CLI and NWS forecast ingest against real fixtures (no network)."""

from __future__ import annotations

import glob
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest  # noqa: F401
from core_fixtures import FIXTURES, load_json
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.cli_ingest import run_cli_ingest
from edgefront_core.db import session_scope
from edgefront_core.forecast_ingest import run_forecast_ingest
from edgefront_core.models import CliProduct, NwsForecast, SourceHealth, Station
from edgefront_core.nws_products import NwsProductLister

NOW = datetime(2026, 11, 24, 17, 30, tzinfo=UTC)


def nosleep(_s: float) -> None:
    return None


def _stations(factory: sessionmaker[Session]) -> None:
    with session_scope(factory) as s:
        for sid, tz, off, x, y in [
            ("KNYC", "America/New_York", "OKX", 34, 45),
            ("KOKC", "America/Chicago", "OUN", 94, 90),
            ("KDFW", "America/Chicago", "FWD", 81, 109),
        ]:
            s.add(
                Station(
                    id=sid, name=sid, city="x", state="XX", tz=tz, cli_location=sid[1:],
                    nws_office=off, grid_x=x, grid_y=y,
                )
            )  # fmt: skip


# ---------------------------------------------------------------- CLI


class FakeCli:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.by_loc: dict[str, list[dict[str, Any]]] = {}
        self.docs: dict[str, dict[str, Any]] = {}
        for p in glob.glob(str(FIXTURES / "nws_cli" / "CLI*.json")):
            doc = json.loads(Path(p).read_text(encoding="utf-8"))
            loc = Path(p).name[3:6]
            self.by_loc.setdefault(loc, []).append(
                {
                    "id": doc["id"],
                    "issuanceTime": doc["issuanceTime"],
                    "issuingOffice": doc["issuingOffice"],
                }
            )
            self.docs[doc["id"]] = doc
        self.fail = fail or set()
        self.product_calls = 0

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path.startswith("/products/types/CLI/locations/"):
            loc = path.rsplit("/", 1)[1]
            if loc in self.fail:
                return httpx.Response(503)
            g = sorted(self.by_loc.get(loc, []), key=lambda x: x["issuanceTime"], reverse=True)
            return httpx.Response(200, json={"@graph": g})
        pid = path.rsplit("/", 1)[1]
        self.product_calls += 1
        return httpx.Response(200, json=self.docs[pid])

    def lister(self) -> NwsProductLister:
        return NwsProductLister(
            httpx.Client(transport=httpx.MockTransport(self.handler)), sleep=nosleep
        )


def test_cli_ingest_stores_dedupes_and_keeps_correction(
    session_factory: sessionmaker[Session],
) -> None:
    _stations(session_factory)
    fake = FakeCli()
    lister = fake.lister()
    first = run_cli_ingest(session_factory, lister, now=lambda: NOW)
    expected = sum(len(fake.by_loc.get(loc, [])) for loc in ("NYC", "OKC", "DFW"))
    assert first.new == expected
    assert first.decode_errors == 0
    calls = fake.product_calls
    second = run_cli_ingest(session_factory, lister, now=lambda: NOW)
    assert second.new == 0
    assert fake.product_calls == calls  # known products are never re-fetched
    with session_scope(session_factory) as s:
        okc = s.scalars(
            select(CliProduct).where(CliProduct.station_id == "KOKC").order_by(CliProduct.issued_at)
        ).all()
        assert [r.is_correction for r in okc] == [False, True]
        assert okc[1].wmo_header == "CDUS44 KOUN 241431 CCA"
        assert all(r.raw_text and r.raw_hash and r.source and r.fetched_at for r in okc)
        h = s.get(SourceHealth, "cli")
        assert h is not None
        assert h.last_success_at is not None


def test_cli_station_failure_does_not_stop_others(session_factory: sessionmaker[Session]) -> None:
    _stations(session_factory)
    res = run_cli_ingest(session_factory, FakeCli(fail={"OKC"}).lister(), now=lambda: NOW)
    assert res.failed_stations == 1
    assert res.new > 0
    with session_scope(session_factory) as s:
        assert s.scalar(select(func.count()).where(CliProduct.station_id == "KOKC")) == 0


def test_cli_all_failing_marks_source_unhealthy(session_factory: sessionmaker[Session]) -> None:
    _stations(session_factory)
    run_cli_ingest(session_factory, FakeCli(fail={"NYC", "OKC", "DFW"}).lister(), now=lambda: NOW)
    with session_scope(session_factory) as s:
        h = s.get(SourceHealth, "cli")
        assert h is not None
        assert h.last_success_at is None
        assert h.last_error is not None


# ---------------------------------------------------------------- forecast


class FakeNws:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_first: dict[str, int] = {}
        self.not_modified = False

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        self.calls.append(path)
        n = self.fail_first.get(path, 0)
        if n:
            self.fail_first[path] = n - 1
            return httpx.Response(500, json={"title": "Unexpected Problem"})
        if self.not_modified and "If-Modified-Since" in req.headers:
            return httpx.Response(304, headers={"Cache-Control": "public, max-age=3600"})
        sid = {"OKX/34,45": "KNYC", "FWD/81,109": "KDFW", "OUN/94,90": "KDFW"}[
            path.split("/gridpoints/")[1].split("/forecast")[0]
        ]
        name = f"nws_forecast/{sid}_forecast{'_hourly' if path.endswith('hourly') else ''}.json"
        return httpx.Response(
            200,
            json=load_json(name),
            headers={
                "Cache-Control": "public, max-age=3598, s-maxage=3600",
                "Last-Modified": "Tue, 24 Nov 2026 17:06:44 GMT",
            },
        )

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


def test_forecast_fetch_cache_304_and_retention(session_factory: sessionmaker[Session]) -> None:
    _stations(session_factory)
    fake = FakeNws()
    c = fake.client()
    r1 = run_forecast_ingest(session_factory, c, now=lambda: NOW, sleep=nosleep)
    assert (r1.updated, r1.failed) == (3, 0)
    assert len(fake.calls) == 6
    # Within max-age: nothing is fetched.
    r2 = run_forecast_ingest(
        session_factory, c, now=lambda: NOW + timedelta(minutes=30), sleep=nosleep
    )
    assert r2.skipped_fresh == 3
    assert len(fake.calls) == 6
    # After expiry: conditional request, 304 → no new row.
    fake.not_modified = True
    later = NOW + timedelta(hours=1, minutes=5)
    r3 = run_forecast_ingest(session_factory, c, now=lambda: later, sleep=nosleep)
    assert r3.not_modified == 3
    with session_scope(session_factory) as s:
        assert s.scalar(select(func.count()).select_from(NwsForecast)) == 3
    # Fresh content repeatedly → at most 3 rows per station kept.
    fake.not_modified = False
    for i in range(4):
        t = NOW + timedelta(hours=3 + 2 * i)
        run_forecast_ingest(session_factory, c, now=lambda t=t: t, sleep=nosleep)  # type: ignore[misc]
    with session_scope(session_factory) as s:
        per = dict(
            s.execute(
                select(NwsForecast.station_id, func.count()).group_by(NwsForecast.station_id)
            ).all()
        )
        assert per == {"KNYC": 3, "KOKC": 3, "KDFW": 3}
        row = s.scalars(select(NwsForecast).where(NwsForecast.station_id == "KDFW")).first()
        assert row is not None
        assert row.periods
        assert row.hourly
        assert len(row.hourly) <= 48
        assert row.update_time is not None
        assert row.source == "api.weather.gov/gridpoints"


def test_forecast_5xx_is_retried_with_backoff(session_factory: sessionmaker[Session]) -> None:
    _stations(session_factory)
    fake = FakeNws()
    fake.fail_first["/gridpoints/FWD/81,109/forecast"] = 2
    slept: list[float] = []
    res = run_forecast_ingest(
        session_factory, fake.client(), now=lambda: NOW, sleep=slept.append, pause_s=0
    )
    assert (res.updated, res.failed) == (3, 0)
    backoff = [d for d in slept if d > 0]
    assert len(backoff) == 2
    assert backoff[1] > backoff[0]  # exponential


def test_forecast_persistent_5xx_fails_one_station_only(
    session_factory: sessionmaker[Session],
) -> None:
    _stations(session_factory)
    fake = FakeNws()
    fake.fail_first["/gridpoints/FWD/81,109/forecast"] = 99
    res = run_forecast_ingest(session_factory, fake.client(), now=lambda: NOW, sleep=nosleep)
    assert (res.updated, res.failed) == (2, 1)
    with session_scope(session_factory) as s:
        h = s.get(SourceHealth, "forecast")
        assert h is not None
        assert h.last_success_at is not None
