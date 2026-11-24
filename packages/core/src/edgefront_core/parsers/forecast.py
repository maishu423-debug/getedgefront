"""NWS gridpoint forecast (12 h periods) and hourly forecast: selection rules (CONTEXT.md §4.3).

Verified on real responses (tests/fixtures/nws_forecast): periods carry `startTime`/`endTime`
with the office's local offset, `isDaytime`, `temperature` + `temperatureUnit` ("F" with
`units=us`), `probabilityOfPrecipitation.value` (%), `shortForecast`, `detailedForecast`. The
first period starts at the issue hour ("Today" may start at 11:00; in the evening the first
period is "Tonight"), so selection uses local dates and end times, never list position.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Period:
    number: int
    name: str
    start: datetime
    end: datetime
    is_daytime: bool
    temperature_f: int | None
    pop_percent: int | None
    short: str | None
    detailed: str | None


def _temp_f(p: dict[str, Any]) -> int | None:
    t = p.get("temperature")
    if t is None:
        return None
    if isinstance(t, dict):  # quantitative-value form (not seen in fixtures; never guessed)
        return None
    unit = p.get("temperatureUnit")
    if unit == "F":
        return int(t)
    return None  # only °F requests are made; anything else is treated as unknown


def _pop(p: dict[str, Any]) -> int | None:
    pop = p.get("probabilityOfPrecipitation") or {}
    v = pop.get("value")
    return int(v) if isinstance(v, int | float) else None


def parse_periods(doc: dict[str, Any]) -> list[Period]:
    out = []
    for p in doc["properties"]["periods"]:
        out.append(
            Period(
                number=int(p["number"]),
                name=str(p.get("name") or ""),
                start=datetime.fromisoformat(p["startTime"]),
                end=datetime.fromisoformat(p["endTime"]),
                is_daytime=bool(p.get("isDaytime")),
                temperature_f=_temp_f(p),
                pop_percent=_pop(p),
                short=p.get("shortForecast") or None,
                detailed=p.get("detailedForecast") or None,
            )
        )
    return out


def _local_date(dt: datetime, tz: ZoneInfo) -> date:
    return dt.astimezone(tz).date()


def today_period(periods: list[Period], now: datetime, tz_name: str) -> Period | None:
    """The daytime period starting today (station local date) that has not ended yet.
    If today's daytime period is over, None — never tomorrow's (§4.3)."""
    tz = ZoneInfo(tz_name)
    today = _local_date(now, tz)
    for p in periods:
        if p.is_daytime and _local_date(p.start, tz) == today and p.end > now:
            return p
    return None


def tonight_period(periods: list[Period], now: datetime, tz_name: str) -> Period | None:
    """The first night period that has not ended and starts today or earlier (local), e.g.
    'Tonight' in the afternoon or 'Overnight' after midnight."""
    tz = ZoneInfo(tz_name)
    today = _local_date(now, tz)
    for p in periods:
        if not p.is_daytime and p.end > now and _local_date(p.start, tz) <= today:
            return p
    return None


@dataclass(frozen=True)
class HourSlot:
    start: datetime
    temperature_f: int | None
    pop_percent: int | None
    short: str | None


def hourly_strip(
    hourly: list[Period], now: datetime, slots: int = 7, step_hours: int = 2
) -> list[HourSlot]:
    """`slots` hours from the current hour in `step_hours` steps (default: next 14 h, 2 h apart).
    A slot whose hour is not in the forecast is omitted, never interpolated."""
    current = next((p for p in hourly if p.start <= now < p.end), None)
    if current is None:
        current = next((p for p in hourly if p.start >= now), None)
    if current is None:
        return []
    by_start = {p.start: p for p in hourly}
    out = []
    for i in range(slots):
        p = by_start.get(current.start + timedelta(hours=i * step_hours))
        if p is not None:
            out.append(HourSlot(p.start, p.temperature_f, p.pop_percent, p.short))
    return out
