"""Unit conversions and derived values (CONTEXT.md §6.1, §6.5)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, overload

HPA_PER_INHG = Decimal("33.8639")

_COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")  # fmt: skip


def c_to_f(c: Decimal | float) -> Decimal:
    return Decimal(str(c)) * Decimal(9) / Decimal(5) + Decimal(32)


@overload
def c_to_f_display(c: None) -> None: ...
@overload
def c_to_f_display(c: Decimal | float) -> int: ...
def c_to_f_display(c: Decimal | float | None) -> int | None:
    """°C → whole °F, rounded half away from zero (§6.1). None stays None."""
    if c is None:
        return None
    f = c_to_f(c)
    # ROUND_HALF_UP on the absolute value == half away from zero.
    rounded = abs(f).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(rounded if f >= 0 else -rounded)


TempPrecision = Literal["tenths_c", "whole_c"]
TempSource = Literal["metar_tgroup", "metar_body", "metar_6h_group", "hfmetar"]


@dataclass(frozen=True)
class TempValue:
    """A temperature as traders need it (v2 Phase 9 B9): the exact °F conversion and the
    whole-°F value, with how precise the source is and where it came from.

    - `f_exact` = °C * 9/5 + 32, never rounded (tenths °C give at most two decimals).
    - `f_rounded` = whole °F, half away from zero (same helper as the rest of the site).
    - `precision`: "tenths_c" (METAR T-group, 6-hour groups) or "whole_c" (METAR body without a
      T-group): a whole-°C value is only good to ±0.5 °C (±0.9 °F) and must be shown as such.
    """

    c: Decimal
    f_exact: Decimal
    f_rounded: int
    precision: TempPrecision
    source: TempSource
    observed_at: datetime


def temp_value(
    c: Decimal | float, precision: TempPrecision, source: TempSource, observed_at: datetime
) -> TempValue:
    dc = Decimal(str(c))
    return TempValue(dc, c_to_f(dc), c_to_f_display(dc), precision, source, observed_at)


def metar_temp_value(
    c: Decimal | float, temp_precision: str | None, observed_at: datetime, *, six_hour: bool = False
) -> TempValue:
    """A METAR temperature → TempValue: 6-hour groups and T-groups are tenths °C; the report
    body (no T-group) is whole °C."""
    if six_hour:
        return temp_value(c, "tenths_c", "metar_6h_group", observed_at)
    if temp_precision == "tenths":
        return temp_value(c, "tenths_c", "metar_tgroup", observed_at)
    return temp_value(c, "whole_c", "metar_body", observed_at)


def rh_percent(temp_c: Decimal | float | None, dewpt_c: Decimal | float | None) -> float | None:
    """Relative humidity from T/Td, Magnus (17.625, 243.04 °C). Always labelled 'computed'."""
    if temp_c is None or dewpt_c is None:
        return None
    t, td = float(temp_c), float(dewpt_c)
    a, b = 17.625, 243.04
    rh = 100.0 * math.exp(a * td / (b + td)) / math.exp(a * t / (b + t))
    return round(min(rh, 100.0), 1)


def compass_point(deg: int | None) -> str | None:
    if deg is None:
        return None
    return _COMPASS[round((deg % 360) / 22.5) % 16]


# Plotting midpoints only; the category is always shown alongside (§6.5).
CLOUD_MIDPOINT = {"CLR": 0, "SKC": 0, "FEW": 19, "SCT": 44, "BKN": 75, "OVC": 100, "VV": 100}
