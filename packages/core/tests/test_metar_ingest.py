"""METAR ingest end to end against the real 36 h corpus (no network)."""

from __future__ import annotations

import copy
import glob
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from core_fixtures import FIXTURES, load_json
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.metar_ingest import (
    RESPONSE_CAP,
    choose_hours,
    fetch_metars,
    plan_batches,
    run_metar_ingest,
    store_reports,
    sync_high_events,
)
from edgefront_core.models import DailyHighEvent, MetarReport, SourceHealth, Station
from edgefront_core.registry import load_registry
from edgefront_core.seed import seed

REPO = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 11, 24, 16, 30, tzinfo=UTC)


def corpus() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for p in sorted(glob.glob(str(FIXTURES / "aviationweather" / "metar_36h_batch*.json"))):
        items += load_json("aviationweather/" + Path(p).name)
    return items


class FakeAwc:
    def __init__(self, items: list[dict[str, Any]], cap: int = RESPONSE_CAP) -> None:
        self.items = items
        self.cap = cap
        self.calls: list[list[str]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        ids = request.url.params["ids"].split(",")
        self.calls.append(ids)
        rows = [x for x in self.items if x["icaoId"] in ids]
        rows.sort(key=lambda x: -int(x["obsTime"]))
        return httpx.Response(200, json=rows[: self.cap])

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> sessionmaker[Session]:
    with session_scope(session_factory) as s:
        seed(s, load_registry(REPO / "data" / "stations.yaml"))
    return session_factory


def test_backfill_then_rerun_is_all_duplicates(seeded: sessionmaker[Session]) -> None:
    items = corpus()
    fake = FakeAwc(items)
    with fake.client() as c:
        first = run_metar_ingest(seeded, c, now=lambda: NOW)
    assert first.new == len(items)
    assert first.errors == 0
    assert first.dup == 0
    assert first.events_added > 0
    with fake.client() as c:
        second = run_metar_ingest(seeded, c, now=lambda: NOW)
    assert (second.new, second.dup, second.events_added, second.events_removed) == (
        0,
        len(items),
        0,
        0,
    )

    with session_scope(seeded) as s:
        per_station = Counter(sid for (sid,) in s.execute(select(MetarReport.station_id)))
        assert len(per_station) == 28
        assert min(per_station.values()) >= 24  # ≥ 24 h of hourly reports each
        h = s.get(SourceHealth, "metar")
        assert h is not None
        assert h.last_success_at is not None
        assert h.last_item_time is not None
        nyc = s.scalars(select(MetarReport).where(MetarReport.station_id == "KNYC")).first()
        assert nyc is not None
        assert nyc.source == "aviationweather.gov/api/data/metar"
        assert nyc.fetched_at is not None
        assert len(nyc.raw_hash) == 64


def test_first_run_backfills_36h_then_3h() -> None:
    assert choose_hours(None, NOW) == 36
    assert choose_hours(datetime(2026, 11, 24, 16, 27, tzinfo=UTC), NOW) == 3
    assert choose_hours(datetime(2026, 11, 24, 10, 0, tzinfo=UTC), NOW) == 36  # outage


def test_cap_hit_splits_batch() -> None:
    items = corpus()
    fake = FakeAwc(items, cap=RESPONSE_CAP)
    ids = sorted({x["icaoId"] for x in items})
    with fake.client() as c:
        got = fetch_metars(c, ids, 36, sleep=lambda _s: None)
    assert len(got) == len(items)  # nothing lost to the cap
    assert len(fake.calls) > 1


def test_planned_batches_stay_under_cap() -> None:
    ids = [f"K{i:03d}" for i in range(28)]
    assert all(len(b) * 36 * 1.6 < RESPONSE_CAP for b in plan_batches(ids, 36))
    assert plan_batches(ids, 3) == [ids]


def _variant(item: dict[str, Any], raw: str) -> dict[str, Any]:
    v = copy.deepcopy(item)
    v["rawOb"] = raw
    return v


def test_correction_links_to_original_and_replaces_its_high(
    seeded: sessionmaker[Session],
) -> None:
    items = [x for x in corpus() if x["icaoId"] == "KLGA"]
    cor = next(x for x in items if x["rawOb"].startswith("METAR KLGA 231851Z COR"))
    # Test-only: the API never returns the original once a COR exists, so build the
    # original from the real COR text with an erroneous temperature.
    original = _variant(
        cor,
        cor["rawOb"]
        .replace(" COR", "")
        .replace("20/11", "35/11")
        .replace("T02000106", "T03500106"),
    )
    others = [x for x in items if x is not cor]
    with session_scope(seeded) as s:
        store_reports(s, [*others, original], NOW)
        st = s.get(Station, "KLGA")
        assert st is not None
        from edgefront_core.climate import climate_date

        day = climate_date(datetime(2026, 11, 23, 18, 51, tzinfo=UTC), st.tz)
        sync_high_events(s, st, day)
        bad = s.scalars(select(DailyHighEvent).where(DailyHighEvent.station_id == "KLGA")).all()
        assert any(float(e.to_c) == 35.0 for e in bad)

    with session_scope(seeded) as s:
        res = store_reports(s, [cor], NOW)
        assert res.corrections_linked == 1
        st = s.get(Station, "KLGA")
        assert st is not None
        sync_high_events(s, st, day)
        row = s.scalars(
            select(MetarReport).where(
                MetarReport.is_correction, MetarReport.raw_text == cor["rawOb"].strip()
            )
        ).one()
        assert row.corrects_report_id is not None
        events = s.scalars(select(DailyHighEvent).where(DailyHighEvent.station_id == "KLGA")).all()
        assert all(float(e.to_c) != 35.0 for e in events)  # erroneous high withdrawn


def test_unknown_station_and_bad_raw_are_counted(seeded: sessionmaker[Session]) -> None:
    good = corpus()[0]
    with session_scope(seeded) as s:
        res = store_reports(
            s,
            [
                _variant(good, good["rawOb"].replace(good["icaoId"], "KZZZ")),
                _variant(good, "garbage"),
            ],
            NOW,
        )
    assert (res.new, res.unknown_station, res.errors) == (0, 1, 1)


def test_events_are_reconciled_not_duplicated(seeded: sessionmaker[Session]) -> None:
    fake = FakeAwc(corpus())
    with fake.client() as c:
        run_metar_ingest(seeded, c, now=lambda: NOW)
    with session_scope(seeded) as s:
        n1 = s.scalar(select(func.count()).select_from(DailyHighEvent))
        for st in s.scalars(select(Station)):
            for day in {e.climate_date for e in s.scalars(select(DailyHighEvent))}:
                sync_high_events(s, st, day)
        n2 = s.scalar(select(func.count()).select_from(DailyHighEvent))
    assert n1 == n2
