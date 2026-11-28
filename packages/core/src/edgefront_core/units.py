"""Unit conversions and derived values (CONTEXT.md §6.1, §6.5)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, overload

HPA_PER_INHG = Decimal("33.8639")

_COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")  # fmt: skip


def c_to_f(c: Decimal | float) -> Decimal:
    return Decimal(str(c)) * Decimal(9) / Decimal(5) + Decimal(32)


def round_half_up(x: Decimal) -> int:
    """NWS rounding (FMH-1 2.6.3): a dropped fraction of .5 or more rounds up; for negative
    numbers only more than .5 rounds down. That is floor(x + 0.5), e.g. 36.5 -> 37 and
    -8.5 -> -8. Not Python's round() (36.5 -> 36) and not "half away from zero" (-8.5 -> -9).
    Exact on Decimal, so no float can flip a .5 case."""
    return math.floor(x + Decimal("0.5"))


@overload
def c_to_f_display(c: None) -> None: ...
@overload
def c_to_f_display(c: Decimal | float) -> int: ...
def c_to_f_display(c: Decimal | float | None) -> int | None:
    """°C -> whole °F with NWS half-up rounding (FMH-1 2.6.3). None stays None."""
    if c is None:
        return None
    return round_half_up(c_to_f(c))


TempPrecision = Literal["tenths_c", "whole_c"]
TempSource = Literal["metar_tgroup", "metar_body", "metar_6h_group", "hfmetar"]


NativeUnit = Literal["F", "C"]


@dataclass(frozen=True)
class TempValue:
    """A temperature as traders need it (v2 Phase 9 B9): the exact °F conversion and the
    whole-°F value, with how precise the source is and where it came from.

    - `f_exact` = °C * 9/5 + 32, never rounded: tenths °C give exactly two decimals, whole °C one.
    - `f_rounded` = whole °F with NWS half-up rounding (`round_half_up`).
    - `f_possible` = the whole-°F readings an ASOS station (which measures in whole °F) could
      have made to produce this °C value: one for a tenths value (none if no whole °F converts to
      it), one or two for a whole-°C value. None at stations that measure in °C (`native_unit`).
    - `precision`: "tenths_c" or "whole_c" (only good to +-0.5 °C = +-0.9 °F).

    All arithmetic is in integers (FMH-1 conversions, owner spec B9):
      tenths: f_x100 = 18*c10 + 3200; f_exact = f_x100/100; f_rounded = floor((f_x100+50)/100)
      whole:  f_x10  = 18*c   + 320;  f_exact = f_x10/10;   f_rounded = floor((f_x10+5)/10)
    and °F -> °C uses nearest rounding (ASOS: verified on 3,031 real METARs; an exact .5 tie
    can't occur when converting a whole °F).
    """

    c: Decimal
    f_exact: Decimal
    f_rounded: int
    f_possible: tuple[int, ...] | None
    precision: TempPrecision
    source: TempSource
    observed_at: datetime


def f_to_c10(f: int) -> int:
    """Whole °F -> tenths °C, nearest (floor(x + 0.5)); x = (f-32)*50/9 is never exactly .5."""
    return (100 * (f - 32) + 9) // 18


def f_to_c(f: int) -> int:
    """Whole °F -> whole °C, nearest; never an exact .5 tie either."""
    return (10 * (f - 32) + 9) // 18


def temp_value(
    c: Decimal | float,
    precision: TempPrecision,
    source: TempSource,
    observed_at: datetime,
    native_unit: NativeUnit = "F",
) -> TempValue:
    """Exact and rounded °F from a °C value on its grid (tenths or whole). A value that is not
    on that grid is refused (ValueError): callers snap source data first, never guess."""
    dc = Decimal(str(c))
    if precision == "tenths_c":
        c10 = dc * 10
        if c10 != c10.to_integral_value():
            raise ValueError(f"{dc} °C is not a tenths value")
        n = int(c10)
        f_x100 = 18 * n + 3200
        f_exact = Decimal(f_x100) / 100
        f_rounded = (f_x100 + 50) // 100
        possible = tuple(f for f in range(f_rounded - 2, f_rounded + 3) if f_to_c10(f) == n)
    else:
        if dc != dc.to_integral_value():
            raise ValueError(f"{dc} °C is not a whole value")
        n = int(dc)
        f_x10 = 18 * n + 320
        f_exact = Decimal(f_x10) / 10
        f_rounded = (f_x10 + 5) // 10
        possible = tuple(f for f in range(f_rounded - 2, f_rounded + 3) if f_to_c(f) == n)
    return TempValue(
        dc, f_exact, f_rounded, possible if native_unit == "F" else None, precision, source,
        observed_at,
    )  # fmt: skip


def metar_temp_value(
    c: Decimal | float,
    temp_precision: str | None,
    observed_at: datetime,
    *,
    six_hour: bool = False,
    native_unit: NativeUnit = "F",
) -> TempValue:
    """A METAR temperature -> TempValue: 6-hour groups and T-groups are tenths °C; the report
    body (no T-group) is whole °C."""
    if six_hour:
        return temp_value(c, "tenths_c", "metar_6h_group", observed_at, native_unit)
    if temp_precision == "tenths":
        return temp_value(c, "tenths_c", "metar_tgroup", observed_at, native_unit)
    return temp_value(c, "whole_c", "metar_body", observed_at, native_unit)


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
