"""CLI decoder tests on real products (fixtures/nws_cli)."""

from __future__ import annotations

import glob
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from core_fixtures import FIXTURES, product_text

from edgefront_core.parsers.cli import parse_cli, to_24h

FILES = sorted(Path(p).name for p in glob.glob(str(FIXTURES / "nws_cli" / "CLI*.json")))


def cli(name: str):  # type: ignore[no-untyped-def]
    return parse_cli(product_text(f"nws_cli/{name}"))


@pytest.mark.parametrize("name", FILES)
def test_every_fixture_decodes_without_errors(name: str) -> None:
    c = cli(name)
    assert c.errors == []
    assert c.climate_date is not None
    assert c.kind in ("final", "preliminary")
    assert c.max.value_f is not None
    assert c.min.value_f is not None
    assert c.issuer is not None
    assert name.startswith(f"CLI{c.location}_")


def test_final_nyc() -> None:
    c = cli("CLINYC_202611240619.json")
    assert (c.issuer, c.climate_date, c.kind, c.valid_as_of_local) == (
        "KOKX",
        date(2026, 11, 23),
        "final",
        None,
    )
    assert (c.max.value_f, c.max.time_local, c.max.normal_f, c.max.departure_f) == (
        69,
        "13:39",
        51,
        18,
    )
    assert (c.min.value_f, c.min.time_local, c.min.normal_f, c.min.departure_f) == (
        50,
        "23:59",
        40,
        10,
    )
    assert (c.precip_in, c.precip_trace) == (Decimal("0.00"), False)
    assert c.is_correction is False


def test_intraday_nyc_valid_today_as_of() -> None:
    c = cli("CLINYC_202611232135.json")
    assert (c.climate_date, c.kind, c.valid_as_of_local) == (
        date(2026, 11, 23),
        "preliminary",
        "16:00",
    )
    assert (c.min.value_f, c.min.time_local) == (58, "07:34")  # lower overnight min came later


def test_morning_issuance_with_trace_and_colon_times() -> None:
    c = cli("CLIAUS_202611241334.json")
    assert (c.climate_date, c.kind, c.valid_as_of_local) == (
        date(2026, 11, 24),
        "preliminary",
        "07:00",
    )
    assert (c.max.value_f, c.max.time_local) == (52, "04:30")
    assert c.precip_in is None
    assert c.precip_trace is True


def test_correction_cca() -> None:
    c = cli("CLIOKC_202611241431.json")
    assert c.is_correction is True
    assert c.bbb == "CCA"
    assert c.climate_date == date(2026, 11, 23)
    assert c.kind == "final"
    original = cli("CLIOKC_202611240737.json")
    assert original.is_correction is False
    assert original.bbb is None


def test_two_intraday_issuances_same_day() -> None:
    a, b = cli("CLIDFW_202611232240.json"), cli("CLIDFW_202611240028.json")
    assert (a.valid_as_of_local, b.valid_as_of_local) == ("16:00", "18:00")
    assert a.climate_date == b.climate_date == date(2026, 11, 23)


def test_valid_as_of_with_minutes() -> None:
    assert cli("CLISDF_202611240022.json").valid_as_of_local == "19:25"


def test_missing_values_are_none_not_zero() -> None:
    text = product_text("nws_cli/CLINYC_202611240619.json")
    text = text.replace(
        "  MAXIMUM         69    139 PM  72    1931  51     18       49",
        "  MAXIMUM         MM",
    ).replace(
        "  YESTERDAY        0.00          1.84 1923", "  YESTERDAY        MM            1.84 1923"
    )
    c = parse_cli(text)
    assert c.max.value_f is None
    assert c.max.time_local is None
    assert "maximum temperature not decoded" in c.errors
    assert c.precip_in is None
    assert c.precip_trace is False


def test_garbage_reports_errors() -> None:
    c = parse_cli("not a product")
    assert c.climate_date is None
    assert "climate summary title not found" in c.errors


@pytest.mark.parametrize(
    ("raw", "out"),
    [("139 PM", "13:39"), ("1159 PM", "23:59"), ("2:53 PM", "14:53"), ("1205 AM", "00:05"),
     ("1200 PM", "12:00"), ("1300 PM", None)],
)  # fmt: skip
def test_to_24h(raw: str, out: str | None) -> None:
    assert to_24h(raw) == out
