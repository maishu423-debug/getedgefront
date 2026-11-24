from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from core_fixtures import load_json

from edgefront_core.parsers.forecast import (
    hourly_strip,
    parse_periods,
    today_period,
    tonight_period,
)

TZ = "America/Chicago"


def dfw() -> Any:
    return parse_periods(load_json("nws_forecast/KDFW_forecast.json"))


def test_parse_real_periods() -> None:
    p = dfw()
    assert p[0].name == "Today"
    assert p[0].is_daytime is True
    assert p[0].temperature_f == 50
    assert p[0].pop_percent == 28
    assert p[1].name == "Tonight"
    assert p[1].temperature_f == 35
    assert p[0].detailed


def test_morning_today_high_and_tonight_low() -> None:
    now = datetime(2026, 11, 24, 17, 30, tzinfo=UTC)  # 11:30 CST
    t, n = today_period(dfw(), now, TZ), tonight_period(dfw(), now, TZ)
    assert t is not None
    assert n is not None
    assert (t.name, t.temperature_f) == ("Today", 50)
    assert (n.name, n.temperature_f) == ("Tonight", 35)


def test_evening_after_daytime_period_ended_is_null_not_tomorrow() -> None:
    now = datetime(2026, 11, 25, 1, 0, tzinfo=UTC)  # 19:00 CST on the 24th
    assert today_period(dfw(), now, TZ) is None  # "Wednesday" (55 °F) must NOT be returned
    n = tonight_period(dfw(), now, TZ)
    assert n is not None
    assert n.name == "Tonight"


def test_after_midnight_tonight_is_the_current_night_period() -> None:
    now = datetime(2026, 11, 25, 8, 0, tzinfo=UTC)  # 02:00 CST on the 25th
    n = tonight_period(dfw(), now, TZ)
    assert n is not None
    assert n.name == "Tonight"  # started yesterday evening, still running
    t = today_period(dfw(), now, TZ)
    assert t is not None
    assert t.name == "Wednesday"  # today's (the 25th) daytime period


def _period(n: int, start: str, end: str, day: bool, temp: int) -> dict[str, Any]:
    return {
        "number": n, "name": f"P{n}", "startTime": start, "endTime": end, "isDaytime": day,
        "temperature": temp, "temperatureUnit": "F",
        "probabilityOfPrecipitation": {"unitCode": "wmoUnit:percent", "value": None},
        "shortForecast": "x", "detailedForecast": "x",
    }  # fmt: skip


def test_dst_spring_forward_day() -> None:
    # 2026-03-08: clocks jump 02:00 CST → 03:00 CDT. Offsets differ across the day.
    doc = {
        "properties": {
            "periods": [
                _period(1, "2026-03-08T00:00:00-06:00", "2026-03-08T06:00:00-05:00", False, 40),
                _period(2, "2026-03-08T06:00:00-05:00", "2026-03-08T18:00:00-05:00", True, 66),
                _period(3, "2026-03-08T18:00:00-05:00", "2026-03-09T06:00:00-05:00", False, 45),
                _period(4, "2026-03-09T06:00:00-05:00", "2026-03-09T18:00:00-05:00", True, 70),
            ]
        }
    }
    p = parse_periods(doc)
    early = datetime(2026, 3, 8, 7, 30, tzinfo=UTC)  # 01:30 CST
    t = today_period(p, early, TZ)
    assert t is not None
    assert t.temperature_f == 66
    evening = datetime(2026, 3, 9, 0, 30, tzinfo=UTC)  # 19:30 CDT on the 8th
    assert today_period(p, evening, TZ) is None
    n = tonight_period(p, evening, TZ)
    assert n is not None
    assert n.temperature_f == 45


def test_hourly_strip_seven_slots_two_hours_apart() -> None:
    h = parse_periods(load_json("nws_forecast/KDFW_forecast_hourly.json"))
    now = h[0].start + timedelta(minutes=20)
    strip = hourly_strip(h, now)
    assert len(strip) == 7
    assert [(s.start - strip[0].start).total_seconds() / 3600 for s in strip] == [
        0, 2, 4, 6, 8, 10, 12,
    ]  # fmt: skip
    assert strip[0].start == h[0].start
    assert all(s.temperature_f is not None for s in strip)


def test_hourly_strip_omits_missing_hours() -> None:
    h = parse_periods(load_json("nws_forecast/KDFW_forecast_hourly.json"))
    gap = [p for p in h if p.start != h[2].start]  # drop the +2 h slot
    strip = hourly_strip(gap, h[0].start)
    assert len(strip) == 6
    assert h[2].start not in [s.start for s in strip]
