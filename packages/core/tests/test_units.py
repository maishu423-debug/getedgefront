from __future__ import annotations

from decimal import Decimal

import pytest

from edgefront_core.units import c_to_f_display, compass_point, rh_percent


@pytest.mark.parametrize(
    ("c", "f"),
    [
        ("20.0", 68),
        ("-4.4", 24),  # 24.08
        ("0.0", 32),
        ("-17.5", 1),  # 0.5 → half away from zero → 1
        ("-18.5", -1),  # -1.3
        ("-20.25", -4),  # -4.45
        ("-20.28", -5),  # -4.504 → -5 (away from zero)
        ("37.5", 100),  # 99.5 → 100
    ],
)
def test_c_to_f_display_half_away_from_zero(c: str, f: int) -> None:
    assert c_to_f_display(Decimal(c)) == f


def test_c_to_f_display_none() -> None:
    assert c_to_f_display(None) is None


def test_rh_magnus() -> None:
    assert rh_percent(Decimal("20.0"), Decimal("16.1")) == pytest.approx(78.2, abs=0.2)
    assert rh_percent(Decimal("10"), Decimal("10")) == 100.0
    assert rh_percent(None, Decimal("1")) is None


def test_compass_point() -> None:
    assert [compass_point(d) for d in (0, 20, 45, 180, 350, 360)] == [
        "N",
        "NNE",
        "NE",
        "S",
        "N",
        "N",
    ]
    assert compass_point(None) is None
