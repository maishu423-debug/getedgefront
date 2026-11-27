"""v2 Phase 9 B6/B8: 5-minute high/low so far, latency percentiles and the rounding check."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.climate import climate_day_bounds
from edgefront_core.db import session_scope
from edgefront_core.hf_store import (
    HfReading,
    hf_day_summary,
    hf_rows,
    latency_report,
    percentile,
    rounding_check,
    row_hash,
    stations_reporting,
    upsert_readings,
)
from edgefront_core.models import MetarReport
from edgefront_core.registry import load_registry
from edgefront_core.seed import seed

CHI = "America/Chicago"


def r(at: datetime, c: int | str | None, dd: str = "V", precision: str = "whole_c") -> HfReading:
    return HfReading(
        "KDFW", at,
        temp_c=None if c is None else Decimal(c),
        temp_precision=None if c is None else precision,
        qc={"temperature": {"dd": dd, "qca": 123, "qcr": 0}},
    )  # fmt: skip


def z(h: int, m: int = 0, day: int = 15) -> datetime:
    return datetime(2026, 7, day, h, m, tzinfo=UTC)


# ---------------------------------------------------------------- high / low so far


def test_lst_day_in_summer_and_the_midnight_boundary() -> None:
    """DST: the LST day of 2026-07-15 in Chicago is 06:00Z → 06:00Z (1 AM → 1 AM CDT). A reading
    at the start counts, one at the end belongs to the next day, readings before are ignored."""
    start, end = climate_day_bounds(date(2026, 7, 15), CHI)
    assert (start, end) == (z(6), z(6, day=16))
    rows = [r(z(5, 55), 10), r(z(6), 20), r(z(12), 30), r(z(5, 55, day=16), 31), r(z(6, day=16), 5)]
    d = hf_day_summary(rows, start, end)
    assert d.readings == 3  # 06:00, 12:00 and 05:55 next morning
    assert d.high is not None
    assert d.low is not None
    assert (d.high.value_c, d.high.observed_at) == (Decimal(31), z(5, 55, day=16))
    assert (d.low.value_c, d.low.observed_at) == (Decimal(20), z(6))


def test_readings_before_the_day_never_count_even_across_midnight() -> None:
    """The 5-minute feed has no 6-hour groups; a cold spell straddling LST midnight only counts
    from the first reading inside the day."""
    start, end = climate_day_bounds(date(2026, 1, 15), CHI)  # winter: 06:00Z
    rows = [r(start - timedelta(minutes=m), -10) for m in (5, 10, 15)] + [r(start, -3)]
    d = hf_day_summary(rows, start, end)
    assert d.low is not None
    assert d.low.value_c == Decimal(-3)
    assert d.readings == 1


def test_a_later_reading_lowers_the_low_and_ties_keep_the_earliest() -> None:
    start, end = z(6), z(6, day=16)
    d = hf_day_summary([r(z(7), 15), r(z(8), 12), r(z(9), 12), r(z(10), 15)], start, end)
    assert d.low is not None
    assert d.high is not None
    assert (d.low.value_c, d.low.observed_at) == (Decimal(12), z(8))
    assert (d.high.value_c, d.high.observed_at) == (Decimal(15), z(7))


def test_missing_temperature_is_counted_never_zero() -> None:
    d = hf_day_summary([r(z(7), None), r(z(8), 4), r(z(9), None)], z(6), z(6, day=16))
    assert d.low is not None
    assert d.low.value_c == Decimal(4)
    assert (d.readings, d.used, d.missing_temp_count) == (3, 1, 2)
    empty = hf_day_summary([r(z(7), None)], z(6), z(6, day=16))
    assert (empty.high, empty.low, empty.missing_temp_count) == (None, None, 1)


def test_qc_flagged_extremes_are_excluded_and_counted() -> None:
    rows = [
        r(z(7), 20),
        r(z(8), 35, dd="Q"),  # questioned: the would-be high
        r(z(9), -5, dd="X"),  # rejected: the would-be low
        r(z(10), 40, dd="B"),
        r(z(11), 22, dd="Z"),  # preliminary, no QC yet: counts
        r(z(12), 18, dd="S"),
    ]
    d = hf_day_summary(rows, z(6), z(6, day=16))
    assert d.high is not None
    assert d.low is not None
    assert (d.high.value_c, d.low.value_c) == (Decimal(22), Decimal(18))
    assert d.excluded_qc_count == 3
    assert d.used == 3


def test_off_grid_values_are_excluded_and_counted() -> None:
    d = hf_day_summary([r(z(7), 20), r(z(8), "25.37", precision="off_grid")], z(6), z(6, day=16))
    assert d.high is not None
    assert d.high.value_c == Decimal(20)
    assert d.excluded_off_grid_count == 1


def test_a_revised_reading_changes_the_high(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as s:
        seed(s, load_registry())
    kw: dict[str, Any] = {"source_file": "f.gz", "file_modified_at": z(8), "fetched_at": z(8)}
    with session_scope(session_factory) as s:
        upsert_readings(s, [r(z(7), 20), r(z(7, 5), 21)], now=z(8), **kw)
    with session_scope(session_factory) as s:
        d = hf_day_summary(hf_rows(s, "KDFW", z(6), z(6, day=16)), z(6), z(6, day=16))
        assert d.high is not None
        assert d.high.value_c == Decimal(21)
    with session_scope(session_factory) as s:
        res = upsert_readings(s, [r(z(7), 23)], now=z(9), **kw)
        assert res.revised == 1
    with session_scope(session_factory) as s:
        rows = hf_rows(s, "KDFW", z(6), z(6, day=16))
        d = hf_day_summary(rows, z(6), z(6, day=16))
        assert d.high is not None
        assert (d.high.value_c, d.high.observed_at) == (Decimal(23), z(7))
        assert [x.revision for x in rows] == [1, 0]


def test_row_hash_ignores_qc_and_trailing_zeros() -> None:
    a = r(z(7), 20, dd="V")
    b = HfReading("KDFW", z(7), temp_c=Decimal("20.00"), temp_precision="whole_c",
                  qc={"temperature": {"dd": "Q"}})  # fmt: skip
    assert row_hash(a) == row_hash(b)
    assert row_hash(a) != row_hash(r(z(7), 21))


# ---------------------------------------------------------------- latency / reporting


def test_percentile_is_nearest_rank() -> None:
    assert percentile([], 0.5) is None
    assert percentile([3.0], 0.95) == 3.0
    vals = [float(x) for x in range(1, 101)]
    assert (percentile(vals, 0.5), percentile(vals, 0.95)) == (50.0, 95.0)


def test_latency_stages_and_late_rows_left_out(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as s:
        seed(s, load_registry())
    now = z(12)
    with session_scope(session_factory) as s:
        for i, delay in enumerate((150, 160, 170, 180)):
            at = now - timedelta(minutes=5 * (i + 1))
            rd = HfReading("KDFW", at, received_at=at + timedelta(seconds=140),
                           temp_c=Decimal(20), temp_precision="whole_c")  # fmt: skip
            t = at + timedelta(seconds=delay)
            upsert_readings(s, [rd], source_file="f.gz", file_modified_at=t - timedelta(seconds=5),
                            fetched_at=t, now=t + timedelta(seconds=1))  # fmt: skip
        old = now - timedelta(hours=3)  # first fetched 2 h late: a backfill row
        upsert_readings(
            s,
            [HfReading("KLAX", old)],
            source_file="g.gz",
            file_modified_at=old,
            fetched_at=old + timedelta(hours=2),
            now=old + timedelta(hours=2),
        )
    with session_scope(session_factory) as s:
        rep = latency_report(s, now, hours=6)
        assert (rep.rows, rep.excluded_late) == (5, 1)
        assert rep.overall["received"].p50_s == 140.0
        assert (rep.overall["fetched"].p50_s, rep.overall["fetched"].p95_s) == (160.0, 180.0)
        assert rep.overall["ingested"].p95_s == 181.0
        assert rep.overall["file_modified"].count == 4
        assert list(rep.per_station) == ["KDFW"]
        assert stations_reporting(s, now, 30) == ["KDFW"]
        assert stations_reporting(s, now, 4) == []


def test_rounding_check_pairs_same_minute(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as s:
        seed(s, load_registry())
    at = z(15, 10)

    def metar(sid: str, c: str, when: datetime) -> MetarReport:
        return MetarReport(station_id=sid, report_type="SPECI", observed_at=when, raw_text=sid,
                           raw_hash=sid + c, temp_c=Decimal(c), temp_precision="tenths",
                           source="t", fetched_at=when)  # fmt: skip

    with session_scope(session_factory) as s:
        s.add(metar("KDFW", "17.2", at))  # 62.96 °F → reads 63 °F → 17 °C
        s.add(metar("KLAX", "17.2", at))
        s.add(metar("KAUS", "17.2", at + timedelta(minutes=1)))  # not the same minute: no pair
        upsert_readings(s, [r(at, 17), HfReading("KLAX", at, temp_c=Decimal(18),
                                                  temp_precision="whole_c"),
                            HfReading("KAUS", at, temp_c=Decimal(17), temp_precision="whole_c")],
                        source_file="f.gz", file_modified_at=at, fetched_at=at, now=at)  # fmt: skip
    with session_scope(session_factory) as s:
        rc = rounding_check(s, at - timedelta(days=1))
        assert (rc.pairs, rc.matches) == (2, 1)
        assert rc.mismatches == [{
            "station": "KLAX", "observed_at": at.isoformat(), "hf_c": 18, "metar_c": "17.2",
            "station_f": 63, "expected_c": 17,
        }]  # fmt: skip
