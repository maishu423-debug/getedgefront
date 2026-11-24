from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from edgefront_core.climate import (
    climate_date,
    climate_day_bounds,
    high_events,
    high_so_far,
)


def utc(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


@dataclass
class R:
    id: int
    observed_at: datetime
    temp_c: Decimal | None
    report_type: str = "METAR"
    is_correction: bool = False
    temp_precision: str | None = "tenths"
    max6h_c: Decimal | None = None


def dec(s: str) -> Decimal:
    return Decimal(s)


# ---------------------------------------------------------------- climate day bounds


def test_lst_day_winter_chicago() -> None:
    assert climate_day_bounds(date(2026, 11, 24), "America/Chicago") == (
        utc(2026, 11, 24, 6),
        utc(2026, 11, 25, 6),
    )


def test_lst_day_in_summer_is_1am_to_1am_clock_time() -> None:
    # July: CDT is UTC-5, but the LST day still starts at 06:00Z = 1:00 AM CDT.
    assert climate_day_bounds(date(2026, 7, 15), "America/Chicago") == (
        utc(2026, 7, 15, 6),
        utc(2026, 7, 16, 6),
    )


@pytest.mark.parametrize("day", [date(2026, 3, 8), date(2026, 11, 1)])
def test_lst_day_is_24h_on_dst_change_days(day: date) -> None:
    start, end = climate_day_bounds(day, "America/New_York")
    assert start == utc(day.year, day.month, day.day, 5)
    assert (end - start).total_seconds() == 24 * 3600


def test_local_basis_follows_clock_on_dst_days() -> None:
    s, e = climate_day_bounds(date(2026, 3, 8), "America/New_York", "LOCAL")
    assert (s, e) == (utc(2026, 3, 8, 5), utc(2026, 3, 9, 4))  # 23 h
    s, e = climate_day_bounds(date(2026, 11, 1), "America/New_York", "LOCAL")
    assert (s, e) == (utc(2026, 11, 1, 4), utc(2026, 11, 2, 5))  # 25 h


def test_phoenix_has_no_dst() -> None:
    assert climate_day_bounds(date(2026, 7, 15), "America/Phoenix")[0] == utc(2026, 7, 15, 7)


def test_climate_date_at_lst_midnight_boundary() -> None:
    # 04:59Z on Jul 15 is 00:59 EDT on the clock but 23:59 EST: still Jul 14 (LST basis).
    assert climate_date(utc(2026, 7, 15, 4, 59), "America/New_York") == date(2026, 7, 14)
    assert climate_date(utc(2026, 7, 15, 5, 0), "America/New_York") == date(2026, 7, 15)
    # On the local-calendar basis the same instant is already Jul 15.
    assert climate_date(utc(2026, 7, 15, 4, 59), "America/New_York", "LOCAL") == date(2026, 7, 15)


# ---------------------------------------------------------------- high so far

NY_DAY = climate_day_bounds(date(2026, 11, 24), "America/New_York")  # 05Z → 05Z


def test_speci_raises_the_high() -> None:
    reports = [
        R(1, utc(2026, 11, 24, 18, 51), dec("10.0")),
        R(2, utc(2026, 11, 24, 19, 10), dec("12.2"), report_type="SPECI"),
        R(3, utc(2026, 11, 24, 19, 51), dec("11.7")),
    ]
    h = high_so_far(reports, *NY_DAY)
    assert h is not None
    assert (h.value_c, h.report_id, h.kind) == (dec("12.2"), 2, "report")
    ev = high_events(reports, *NY_DAY)
    assert [(e.from_c, e.to_c, e.report_id) for e in ev] == [(dec("10.0"), dec("12.2"), 2)]


def test_reports_outside_the_day_are_ignored() -> None:
    reports = [
        R(1, utc(2026, 11, 24, 4, 51), dec("20.0")),  # 23:51 EST on the 23rd
        R(2, utc(2026, 11, 24, 5, 51), dec("8.0")),
    ]
    h = high_so_far(reports, *NY_DAY)
    assert h is not None
    assert h.value_c == dec("8.0")


def test_six_hour_window_straddling_midnight_is_excluded() -> None:
    # 05:51Z report carries the 00-06Z max; NY's LST day starts at 05Z, so the window
    # straddles midnight and must not count for either day.
    r = R(1, utc(2026, 11, 24, 5, 51), dec("8.0"), max6h_c=dec("15.0"))
    h = high_so_far([r], *NY_DAY)
    assert h is not None
    assert (h.value_c, h.kind) == (dec("8.0"), "report")
    prev = climate_day_bounds(date(2026, 11, 23), "America/New_York")
    assert high_so_far([r], *prev) is None


def test_six_hour_window_inside_the_day_counts() -> None:
    # Chicago LST day is 06Z → 06Z; the 17:53Z report's 12-18Z window is inside.
    day = climate_day_bounds(date(2026, 11, 24), "America/Chicago")
    reports = [
        R(1, utc(2026, 11, 24, 16, 53), dec("10.0")),
        R(2, utc(2026, 11, 24, 17, 53), dec("10.6"), max6h_c=dec("11.1")),
    ]
    h = high_so_far(reports, *day)
    assert h is not None
    assert (h.value_c, h.kind, h.report_id) == (dec("11.1"), "max6h", 2)


def test_six_hour_window_ending_exactly_at_day_end_counts() -> None:
    day = climate_day_bounds(date(2026, 11, 24), "America/Chicago")  # ends 25th 06Z
    r = R(1, utc(2026, 11, 25, 5, 53), dec("3.0"), max6h_c=dec("4.4"))
    h = high_so_far([r], *day)
    assert h is not None
    assert (h.value_c, h.kind) == (dec("4.4"), "max6h")


def test_missing_temperature_is_skipped_and_first_valid_is_baseline() -> None:
    reports = [
        R(1, utc(2026, 11, 24, 6, 51), None),
        R(2, utc(2026, 11, 24, 7, 51), dec("5.0")),
        R(3, utc(2026, 11, 24, 8, 51), dec("6.1")),
    ]
    h = high_so_far(reports, *NY_DAY)
    assert h is not None
    assert h.value_c == dec("6.1")
    ev = high_events(reports, *NY_DAY)
    assert [(e.from_c, e.to_c) for e in ev] == [(dec("5.0"), dec("6.1"))]


def test_no_temperatures_means_no_high() -> None:
    assert high_so_far([R(1, utc(2026, 11, 24, 6, 51), None)], *NY_DAY) is None


def test_correction_replaces_original() -> None:
    reports = [
        R(1, utc(2026, 11, 24, 12, 51), dec("31.0")),  # erroneous original
        R(2, utc(2026, 11, 24, 12, 51), dec("13.0"), is_correction=True),
        R(3, utc(2026, 11, 24, 13, 51), dec("12.0")),
    ]
    h = high_so_far(reports, *NY_DAY)
    assert h is not None
    assert (h.value_c, h.report_id) == (dec("13.0"), 2)


def test_tie_keeps_earliest_report() -> None:
    reports = [
        R(1, utc(2026, 11, 24, 12, 51), dec("13.0")),
        R(2, utc(2026, 11, 24, 13, 51), dec("13.0")),
    ]
    h = high_so_far(reports, *NY_DAY)
    assert h is not None
    assert h.report_id == 1
    assert high_events(reports, *NY_DAY) == []


def test_whole_precision_is_reported() -> None:
    h = high_so_far(
        [R(1, utc(2026, 11, 24, 12, 48), dec("14"), temp_precision="whole", report_type="SPECI")],
        *NY_DAY,
    )
    assert h is not None
    assert h.precision == "whole"
