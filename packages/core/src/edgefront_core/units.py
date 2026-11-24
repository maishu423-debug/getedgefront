"""Unit conversions and derived values (CONTEXT.md §6.1, §6.5)."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from typing import overload

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
