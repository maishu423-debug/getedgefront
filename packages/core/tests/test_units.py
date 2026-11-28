from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from edgefront_core.units import (
    c_to_f_display,
    compass_point,
    f_to_c,
    f_to_c10,
    metar_temp_value,
    rh_percent,
    round_half_up,
    temp_value,
)

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("c", "f"),
    [
        ("20.0", 68),
        ("-4.4", 24),  # 24.08
        ("0.0", 32),
        ("-17.5", 1),  # 0.5 → NWS half-up → 1
        ("-18.5", -1),  # -1.3
        ("-20.25", -4),  # -4.45
        ("-20.28", -5),  # -4.504 → -5 (floor(-4.004))
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


@pytest.mark.parametrize("case", _CASES["cases"], ids=lambda c: f"{c['c']}C-{c['precision']}")
def test_shared_temperature_vectors(case: dict[str, Any]) -> None:
    # The same file drives apps/web/src/lib/temp.test.ts: Python and TypeScript must agree.
    t = temp_value(Decimal(str(case["c"])), case["precision"], "metar_tgroup", NOW)
    assert t.f_exact == Decimal(str(case["f_exact"]))
    assert t.f_rounded == case["f_rounded"]
    assert list(t.f_possible or ()) == case["f_possible"]


def test_nws_half_up_not_python_round_nor_half_away_from_zero() -> None:
    assert round_half_up(Decimal("36.5")) == 37  # Python round(36.5) == 36
    assert round_half_up(Decimal("-8.5")) == -8  # half away from zero would give -9
    assert round_half_up(Decimal("-8.51")) == -9
    assert c_to_f_display(Decimal("2.5")) == 37
    assert c_to_f_display(Decimal("-22.5")) == -8


def test_metar_temp_value_precision_and_source() -> None:
    t = metar_temp_value(Decimal("17.2"), "tenths", NOW)
    assert (t.precision, t.source, t.f_possible) == ("tenths_c", "metar_tgroup", (63,))
    body = metar_temp_value(Decimal("17"), "whole", NOW)
    assert (body.precision, body.source, body.f_exact, body.f_rounded, body.f_possible) == (
        "whole_c", "metar_body", Decimal("62.6"), 63, (62, 63),
    )  # fmt: skip
    six = metar_temp_value(Decimal("-3.3"), "tenths", NOW, six_hour=True)
    assert (six.precision, six.source) == ("tenths_c", "metar_6h_group")
    assert metar_temp_value(Decimal("5"), None, NOW).precision == "whole_c"  # never overstate


def test_stations_measuring_in_celsius_have_no_possible_f_readings() -> None:
    assert metar_temp_value(Decimal("-2.0"), "tenths", NOW, native_unit="C").f_possible is None


def test_values_off_their_grid_are_refused_not_guessed() -> None:
    with pytest.raises(ValueError, match="not a tenths value"):
        temp_value(Decimal("17.25"), "tenths_c", "hfmetar", NOW)
    with pytest.raises(ValueError, match="not a whole value"):
        temp_value(Decimal("17.2"), "whole_c", "hfmetar", NOW)


def test_f_to_c_conversions_are_nearest_and_never_tie() -> None:
    assert (f_to_c10(63), f_to_c10(64), f_to_c10(0)) == (172, 178, -178)
    assert (f_to_c(62), f_to_c(63), f_to_c(31), f_to_c(30)) == (17, 17, -1, -1)
    # (f-32)*5/9 is never exactly x.5 for whole f, so the tie rule never matters here
    assert all((10 * (f - 32)) % 18 != 9 for f in range(-60, 131))
