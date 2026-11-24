from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.models import MarketKind, Station, StationVenue, Venue
from edgefront_core.registry import StationEntry, load_registry
from edgefront_core.seed import seed

REPO = Path(__file__).resolve().parents[3]
STATIONS = REPO / "data" / "stations.yaml"


def test_real_registry_is_valid() -> None:
    entries = load_registry(STATIONS)
    assert len(entries) == 28
    by_id = {e.id: e for e in entries}
    assert by_id["KNYC"].tz == "America/New_York"
    assert by_id["KPHX"].tz == "America/Phoenix"
    assert by_id["KSDF"].tz == "America/Kentucky/Louisville"
    assert all(v.verified is False for e in entries for v in e.venues)
    assert {v.venue for v in by_id["KATL"].venues} == {
        Venue.kalshi,
        Venue.polymarket,
        Venue.robinhood,
    }


def _entry(**kw: object) -> StationEntry:
    base: dict[str, object] = {
        "id": "KTST",
        "name": "Test",
        "city": "Test",
        "state": "TX",
        "tz": "America/Chicago",
        "venues": [{"venue": "kalshi", "kind": "high"}],
    }
    base.update(kw)
    return StationEntry.model_validate(base)


def test_rejects_unknown_tz() -> None:
    with pytest.raises(ValidationError, match="unknown IANA time zone"):
        _entry(tz="America/Nowhere")


def test_rejects_verified_without_evidence() -> None:
    with pytest.raises(ValidationError, match="requires rules_url"):
        _entry(venues=[{"venue": "kalshi", "kind": "high", "verified": True}])


def test_rejects_duplicate_venue_kind() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        _entry(venues=[{"venue": "kalshi", "kind": "high"}, {"venue": "kalshi", "kind": "high"}])


def test_high_and_low_for_same_venue_allowed() -> None:
    e = _entry(venues=[{"venue": "kalshi", "kind": "high"}, {"venue": "kalshi", "kind": "low"}])
    assert len(e.venues) == 2


def test_seed_real_registry_is_idempotent(session_factory: sessionmaker[Session]) -> None:
    entries = load_registry(STATIONS)
    with session_scope(session_factory) as s:
        first = seed(s, entries)
    assert len(first.stations_inserted) == 28
    assert first.venues_inserted == sum(len(e.venues) for e in entries)
    assert first.unverified_venues == first.venues_inserted

    with session_scope(session_factory) as s:
        second = seed(s, entries)
    assert not second.changed

    with session_scope(session_factory) as s:
        assert s.query(Station).count() == 28
        nyc = s.get(Station, "KNYC")
        assert nyc is not None
        assert nyc.dsm_location == "NYC"
        assert nyc.active


def test_seed_null_never_overwrites_and_venues_follow_yaml(
    session_factory: sessionmaker[Session],
) -> None:
    with session_scope(session_factory) as s:
        seed(s, [_entry(dsm_location="TST")])
    # dsm_location removed from YAML (null) and venue switched high -> low.
    with session_scope(session_factory) as s:
        res = seed(s, [_entry(venues=[{"venue": "kalshi", "kind": "low"}])])
    assert res.venues_inserted == 1
    assert res.venues_deleted == 1

    with session_scope(session_factory) as s:
        st = s.get(Station, "KTST")
        assert st is not None
        assert st.dsm_location == "TST"
        kinds = [v.market_kind for v in s.scalars(select(StationVenue))]
        assert kinds == [MarketKind.low]


def test_seed_deactivates_missing_station(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as s:
        seed(s, [_entry(), _entry(id="KABC")])
    with session_scope(session_factory) as s:
        res = seed(s, [_entry()])
    assert res.stations_deactivated == ["KABC"]
    with session_scope(session_factory) as s:
        abc = s.get(Station, "KABC")
        assert abc is not None
        assert abc.active is False
