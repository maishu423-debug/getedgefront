"""Enrichment end to end against real saved responses (no network)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from core_fixtures import fixture_path
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.enrich_stations import Enricher
from edgefront_core.models import Station
from edgefront_core.registry import StationEntry
from edgefront_core.seed import seed

NOW = datetime(2026, 11, 24, 16, 0, tzinfo=UTC)

ROUTES = {
    ("aviationweather.gov", "/api/data/stationinfo"): "aviationweather/stationinfo_28.json",
    ("api.weather.gov", "/stations/KNYC"): "nws/station_KNYC.json",
    ("api.weather.gov", "/points/40.7833,-73.9667"): "nws/points_40.7833_-73.9667.json",
    ("api.weather.gov", "/products/types/DSM/locations/NYC"): "nws_products/dsm_list_NYC.json",
    (
        "api.weather.gov",
        "/products/797f72b6-cfe9-47fb-96e8-55fc65f16c4d",
    ): "nws_products/dsm_NYC_797f72b6.json",
    ("api.weather.gov", "/products/types/PFM/locations/OKX"): "nws_products/pfm_list_OKX.json",
    (
        "api.weather.gov",
        "/products/ad398d3d-a747-4d9d-8ce2-5f0544a05b0e",
    ): "nws_products/pfm_OKX_ad398d3d.json",
}


def _handler(request: httpx.Request) -> httpx.Response:
    rel = ROUTES.get((request.url.host, request.url.path))
    if rel is None:
        return httpx.Response(404, json={"status": 404})
    return httpx.Response(200, content=fixture_path(rel).read_bytes())


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(_handler))


def _seed_knyc(factory: sessionmaker[Session], dsm: str | None = None) -> None:
    entry = StationEntry.model_validate(
        {
            "id": "KNYC",
            "name": "New York · Central Park",
            "city": "New York",
            "state": "NY",
            "tz": "America/New_York",
            "dsm_location": dsm,
            "venues": [{"venue": "kalshi", "kind": "high"}],
        }
    )
    with session_scope(factory) as s:
        seed(s, [entry])


def _enricher(client: httpx.Client) -> Enricher:
    return Enricher(client, now=lambda: NOW, pause=lambda: None, sleep=lambda _s: None)


def test_enrich_knyc_from_real_responses(
    session_factory: sessionmaker[Session], client: httpx.Client
) -> None:
    _seed_knyc(session_factory)
    with session_scope(session_factory) as s:
        [rep] = _enricher(client).run(s)

    assert rep.flags == []
    assert rep.tz_ok is True
    assert rep.dsm == "NYC"
    assert rep.pfm == "Central Park-New York NY"
    with session_scope(session_factory) as s:
        st = s.get(Station, "KNYC")
        assert st is not None
        assert (st.lat, st.lon) == (40.78333, -73.96667)
        assert st.elevation_m == 46.9
        assert st.official_name == "New York City, Central Park"
        assert (st.nws_office, st.grid_x, st.grid_y) == ("OKX", 34, 45)
        assert st.dsm_location == "NYC"
        assert st.pfm_point == "Central Park-New York NY"
        assert st.enriched_at is not None
        assert st.name == "New York · Central Park"  # display name untouched


def test_enrich_is_idempotent(session_factory: sessionmaker[Session], client: httpx.Client) -> None:
    _seed_knyc(session_factory)
    with session_scope(session_factory) as s:
        _enricher(client).run(s)
    with session_scope(session_factory) as s:
        [rep] = _enricher(client).run(s)
    assert rep.changed == []


def test_stale_dsm_is_not_written(
    session_factory: sessionmaker[Session], client: httpx.Client
) -> None:
    _seed_knyc(session_factory)
    later = Enricher(
        client,
        now=lambda: datetime(2026, 12, 30, tzinfo=UTC),
        pause=lambda: None,
        sleep=lambda _s: None,
    )
    with session_scope(session_factory) as s:
        [rep] = later.run(s)
    assert rep.dsm is None
    assert "stale" in rep.dsm_note
    with session_scope(session_factory) as s:
        st = s.get(Station, "KNYC")
        assert st is not None
        assert st.dsm_location is None


def test_unconfirmed_stored_value_is_flagged_not_cleared(
    session_factory: sessionmaker[Session], client: httpx.Client
) -> None:
    _seed_knyc(session_factory, dsm="XYZ")
    with session_scope(session_factory) as s:
        [rep] = _enricher(client).run(s)
    assert any("stored dsm_location XYZ not confirmed" in f for f in rep.flags)
    with session_scope(session_factory) as s:
        st = s.get(Station, "KNYC")
        assert st is not None
        assert st.dsm_location == "XYZ"
