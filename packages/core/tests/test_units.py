from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from edgefront_core.units import (
    c_to_f_display,
    compass_point,
    metar_temp_value,
    rh_percent,
    temp_value,
)

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


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


# ---------------------------------------------------------------- v2 Phase 9 B9: TempValue

_CASES = json.loads((Path(__file__).parent / "fixtures" / "temp_cases.json").read_text("utf-8"))


@pytest.mark.parametrize("case", _CASES["cases"], ids=lambda c: f"{c['c']}C")
def test_temp_value_exact_and_rounded_shared_cases(case: dict[str, float]) -> None:
    # The same file drives apps/web/src/lib/temp.test.ts: Python and TypeScript must agree.
    t = temp_value(Decimal(str(case["c"])), "tenths_c", "metar_tgroup", NOW)
    assert t.f_exact == Decimal(str(case["f_exact"]))
    assert t.f_rounded == case["f_rounded"]


def test_metar_temp_value_precision_and_source() -> None:
    assert metar_temp_value(Decimal("17.2"), "tenths", NOW).precision == "tenths_c"
    assert metar_temp_value(Decimal("17.2"), "tenths", NOW).source == "metar_tgroup"
    body = metar_temp_value(Decimal("17"), "whole", NOW)
    assert (body.precision, body.source, body.f_exact, body.f_rounded) == (
        "whole_c", "metar_body", Decimal("62.6"), 63,
    )  # fmt: skip
    six = metar_temp_value(Decimal("-3.3"), "tenths", NOW, six_hour=True)
    assert (six.precision, six.source) == ("tenths_c", "metar_6h_group")
    assert (
        metar_temp_value(Decimal("5"), None, NOW).precision == "whole_c"
    )  # unknown → never overstate
    assert metar_temp_value(Decimal("5"), None, NOW).observed_at == NOW
