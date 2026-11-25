"""DSM ingest with both fetchers against real fixtures (no network)."""

from __future__ import annotations

import glob
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from core_fixtures import FIXTURES
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.dsm_ingest import IemDsmFetcher, NwsApiDsmFetcher, run_dsm_ingest
from edgefront_core.models import DsmProduct, SourceHealth, Station
from edgefront_core.nws_products import NwsProductLister

NOW = datetime(2026, 11, 24, 17, 0, tzinfo=UTC)


def _iem_products() -> dict[str, list[tuple[str, str, str]]]:
    """loc -> [(product_id, entered, filename)] from the fixture README."""
    out: dict[str, list[tuple[str, str, str]]] = {}
    readme = (FIXTURES / "iem_dsm" / "README.md").read_text(encoding="utf-8")
    for fname, pid in re.findall(r"`(DSM\w+\.txt)` \| \S+/nwstext/(\S+) \|", readme):
        entered = f"{pid[:4]}-{pid[4:6]}-{pid[6:8]}T{pid[8:10]}:{pid[10:12]}:00Z"
        out.setdefault(fname[3:6], []).append((pid, entered, fname))
    return out


class FakeIem:
    def __init__(self, down: bool = False) -> None:
        self.products = _iem_products()
        self.down = down
        self.calls = 0

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.down:
            return httpx.Response(503, text="Service Unavailable")
        if req.url.path.endswith("/list.json"):
            loc = req.url.params["pil"][3:]
            day = req.url.params["date"]
            rows = [
                {"entered": e, "pil": f"DSM{loc}", "product_id": pid, "cccc": pid.split("-")[1]}
                for pid, e, _ in self.products.get(loc, [])
                if e.startswith(day)
            ]
            return httpx.Response(200, json={"data": rows})
        pid = req.url.path.rsplit("/", 1)[1]
        for items in self.products.values():
            for p, _, fname in items:
                if p == pid:
                    return httpx.Response(
                        200, text=(FIXTURES / "iem_dsm" / fname).read_text("utf-8")
                    )
        return httpx.Response(404)

    def fetcher(self) -> IemDsmFetcher:
        return IemDsmFetcher(
            httpx.Client(transport=httpx.MockTransport(self.handler)),
            sleep=lambda _s: None,
        )


class FakeNwsDsm:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}
        self.by_loc: dict[str, list[dict[str, Any]]] = {}
        for p in glob.glob(str(FIXTURES / "nws_dsm" / "DSM*.json")):
            doc = json.loads(Path(p).read_text(encoding="utf-8"))
            self.docs[doc["id"]] = doc
            self.by_loc.setdefault(Path(p).name[3:6], []).append(
                {
                    "id": doc["id"],
                    "issuanceTime": doc["issuanceTime"],
                    "issuingOffice": doc["issuingOffice"],
                }
            )

    def handler(self, req: httpx.Request) -> httpx.Response:
        if "/locations/" in req.url.path:
            loc = req.url.path.rsplit("/", 1)[1]
            g = sorted(self.by_loc.get(loc, []), key=lambda x: x["issuanceTime"], reverse=True)
            return httpx.Response(200, json={"@graph": g})
        return httpx.Response(200, json=self.docs[req.url.path.rsplit("/", 1)[1]])

    def fetcher(self) -> NwsApiDsmFetcher:
        client = httpx.Client(transport=httpx.MockTransport(self.handler))
        return NwsApiDsmFetcher(NwsProductLister(client, sleep=lambda _s: None))


def _stations(factory: sessionmaker[Session]) -> None:
    with session_scope(factory) as s:
        for sid, src in [("KLGA", "iem"), ("KPHL", "iem"), ("KDFW", "iem"), ("KNYC", "nws_api")]:
            s.add(
                Station(
                    id=sid, name=sid, city="x", state="XX", tz="America/New_York",
                    dsm_location=sid[1:], dsm_source=src,
                )
            )  # fmt: skip


def _fetchers(iem: FakeIem) -> dict[str, Any]:
    return {"iem": iem.fetcher(), "nws_api": FakeNwsDsm().fetcher()}


def test_both_sources_store_and_rerun_adds_nothing(session_factory: sessionmaker[Session]) -> None:
    _stations(session_factory)
    iem = FakeIem()
    fetchers = _fetchers(iem)
    stats = run_dsm_ingest(session_factory, fetchers, now=lambda: NOW)
    assert stats["iem"].new > 0
    assert stats["nws_api"].new > 0
    assert stats["iem"].decode_errors == 0
    # PHL's final was transmitted twice (05:16Z and 05:46Z, identical): stored once.
    assert stats["iem"].dup >= 1
    with session_scope(session_factory) as s:
        n = s.scalar(select(func.count()).select_from(DsmProduct))
        phl_finals = s.scalars(
            select(DsmProduct).where(
                DsmProduct.station_id == "KPHL", DsmProduct.issue_key == "FINAL"
            )
        ).all()
        assert len({(r.climate_date, r.raw_hash) for r in phl_finals}) == len(phl_finals)
        lga = s.scalars(
            select(DsmProduct).where(
                DsmProduct.station_id == "KLGA", DsmProduct.issue_key == "0700"
            )
        ).first()
        assert lga is not None
        assert (lga.source, lga.issuer, lga.report_kind, lga.wind_speed_unit) == (
            "iem", "KZNY", "so_far", "mph",
        )  # fmt: skip
        assert lga.wmo_header == "CDUS27 KZNY"
        nyc = s.scalars(select(DsmProduct).where(DsmProduct.station_id == "KNYC")).first()
        assert nyc is not None
        assert nyc.source == "nws_api"
        for key in ("dsm_iem", "dsm_nws"):
            h = s.get(SourceHealth, key)
            assert h is not None
            assert h.last_success_at is not None
    calls = iem.calls
    again = run_dsm_ingest(session_factory, fetchers, now=lambda: NOW)
    assert again["iem"].new == 0
    assert again["nws_api"].new == 0
    assert iem.calls - calls <= 3  # one list call per IEM station, no text re-fetches
    with session_scope(session_factory) as s:
        assert s.scalar(select(func.count()).select_from(DsmProduct)) == n


def test_iem_down_degrades_gracefully(session_factory: sessionmaker[Session]) -> None:
    _stations(session_factory)
    run_dsm_ingest(session_factory, _fetchers(FakeIem()), now=lambda: NOW)
    with session_scope(session_factory) as s:
        before = s.scalar(select(func.count()).select_from(DsmProduct))
    later = datetime(2026, 11, 24, 17, 15, tzinfo=UTC)
    stats = run_dsm_ingest(session_factory, _fetchers(FakeIem(down=True)), now=lambda: later)
    assert stats["iem"].failed == 3
    assert stats["nws_api"].failed == 0
    with session_scope(session_factory) as s:
        iem = s.get(SourceHealth, "dsm_iem")
        nws = s.get(SourceHealth, "dsm_nws")
        assert iem is not None
        assert nws is not None
        assert iem.last_error_at is not None
        assert iem.last_success_at is not None
        assert iem.last_error_at.replace(tzinfo=UTC) > iem.last_success_at.replace(tzinfo=UTC)
        assert nws.last_success_at is not None
        assert nws.last_success_at.replace(tzinfo=UTC) == later
        # Stored DSMs are kept and still served.
        assert s.scalar(select(func.count()).select_from(DsmProduct)) == before


def test_station_without_fetcher_is_reported(session_factory: sessionmaker[Session]) -> None:
    _stations(session_factory)
    stats = run_dsm_ingest(session_factory, {"iem": FakeIem().fetcher()}, now=lambda: NOW)
    assert stats["nws_api"].failed == 1


def test_iem_client_sends_our_real_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Owner A2: never hide our identity from an upstream; IEM gets the NWS User-Agent."""
    import edgefront_core.http as http_mod
    from edgefront_core.settings import Settings

    cfg = Settings(_env_file=None, contact_email="ops@example.org")
    monkeypatch.setattr(http_mod, "get_settings", lambda: cfg)
    with IemDsmFetcher.make_client() as c:
        assert c.headers["User-Agent"] == "EdgeFront/1.0 (getedgefront.com; ops@example.org)"
