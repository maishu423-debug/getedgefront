"""Weekly native-unit drift check (v2 Phase 9, Q36)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.models import MetarReport, Station
from edgefront_core.native_unit_check import (
    check_native_units,
    judge,
    near_whole_f,
    run_native_unit_check,
)
from edgefront_core.registry import load_registry
from edgefront_core.seed import seed
from edgefront_core.units import f_to_c10

NOW = datetime(2026, 11, 27, 12, tzinfo=UTC)


def _report(sid: str, i: int, c10: int, *, days_ago: float = 1) -> MetarReport:
    at = NOW - timedelta(days=days_ago, minutes=i)
    raw = f"METAR {sid} {i} T{c10}"
    return MetarReport(
        station_id=sid, report_type="METAR", observed_at=at, raw_text=raw, raw_hash=f"{sid}{i}",
        temp_c=Decimal(c10) / 10, temp_precision="tenths", source="test", fetched_at=at,
    )  # fmt: skip


def test_near_whole_f() -> None:
    assert near_whole_f(Decimal("17.2"))  # 62.96 °F
    assert not near_whole_f(Decimal("17.5"))  # 63.5 °F
    assert near_whole_f(Decimal("-2.0")) is False  # 28.4 °F


def test_judge_thresholds() -> None:
    assert judge("F", 100, 97) == "ok"
    assert judge("F", 100, 60) == "drift"
    assert judge("C", 100, 20) == "ok"
    assert judge("C", 100, 90) == "drift"
    assert judge("F", 10, 0) == "too_few"


def test_registry_seeds_kbkf_as_celsius(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as s:
        seed(s, load_registry())
    with session_factory() as s:
        units = dict(s.execute(select(Station.id, Station.native_temp_unit)).tuples().all())
    assert units["KBKF"] == "C"
    assert units["KDFW"] == "F"
    assert sum(u == "F" for u in units.values()) == 27


def test_check_flags_a_station_whose_data_stop_matching(
    session_factory: sessionmaker[Session],
) -> None:
    with session_scope(session_factory) as s:
        seed(s, load_registry())
        # KDFW (registry F): tenths that come from whole °F readings -> ok
        s.add_all(_report("KDFW", i, f_to_c10(40 + i)) for i in range(60))
        # KBKF (registry C): every tenth of a degree -> mostly not on whole °F -> ok
        s.add_all(_report("KBKF", i, -20 + i) for i in range(60))
        # KORD (registry F) but real tenths -> drift
        s.add_all(_report("KORD", i, 100 + i) for i in range(60))
        # old reports are outside the 7-day window
        s.add_all(_report("KLAX", i, 100 + i, days_ago=10) for i in range(60))
    with session_factory() as s:
        by = {r.station_id: r for r in check_native_units(s, NOW)}
    assert (by["KDFW"].verdict, by["KDFW"].share) == ("ok", 1.0)
    assert by["KBKF"].verdict == "ok"
    assert by["KORD"].verdict == "drift"
    assert by["KLAX"].verdict == "too_few"
    results = run_native_unit_check(session_factory, NOW)
    assert [r.station_id for r in results if r.verdict == "drift"] == ["KORD"]
