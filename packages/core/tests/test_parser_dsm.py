"""DSM decoder tests on real products (fixtures/iem_dsm via IEM, fixtures/nws_dsm via NWS)."""

from __future__ import annotations

import glob
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from core_fixtures import FIXTURES, product_text

from edgefront_core.parsers.dsm import climate_date_for, parse_dsm

IEM = sorted(Path(p).name for p in glob.glob(str(FIXTURES / "iem_dsm" / "DSM*.txt")))
NWS = sorted(Path(p).name for p in glob.glob(str(FIXTURES / "nws_dsm" / "DSM*.json")))


def iem(name: str) -> str:
    return (FIXTURES / "iem_dsm" / name).read_text(encoding="utf-8")


def test_fixture_coverage() -> None:
    assert len({n[3:6] for n in IEM}) >= 12
    assert {n[3:6] for n in NWS} == {"NYC", "MSP", "SAT"}


@pytest.mark.parametrize("name", IEM)
def test_every_iem_fixture_decodes(name: str) -> None:
    d = parse_dsm(iem(name))
    assert d.errors == []
    assert d.station == "K" + name[3:6]
    assert d.max_f is not None
    assert d.min_f is not None
    assert d.kind in ("so_far", "final")
    assert d.gust.speed_mph is not None


@pytest.mark.parametrize("name", NWS)
def test_every_nws_fixture_decodes(name: str) -> None:
    d = parse_dsm(product_text(f"nws_dsm/{name}"))
    assert d.errors == []
    assert d.station == "K" + name[3:6]


def test_intraday_lga_0700() -> None:
    d = parse_dsm(
        "KLGA DS 0700 24/11 510048/ 440659// 70/ 44//0070016/00/00/00/00/00/\n"
        "00/00/00/-/-/-/-/-/-/-/-/-/-/-/-/-/-/-/-/-/-/31210418/30270421=\n"
    )
    assert (d.kind, d.issue_time_local, d.issue_key, d.day, d.month) == (
        "so_far", "07:00", "0700", 24, 11,
    )  # fmt: skip
    assert (d.max_f, d.max_time_local, d.min_f, d.min_time_local) == (51, "00:48", 44, "06:59")
    assert d.precip_in == Decimal("0.00")
    assert (d.wind.dir_deg, d.wind.speed_mph, d.wind.time_local) == (310, 21, "04:18")
    assert (d.gust.dir_deg, d.gust.speed_mph, d.gust.time_local) == (300, 27, "04:21")


def test_final_bos_matches_cli() -> None:
    # CLI BOS 23/11 final: max 69 at 14:01, min 48 at 23:59, precip 0.78,
    # highest wind 22 mph from 40°, highest gust 32 mph from 300° (WIND (MPH) section).
    d = parse_dsm(iem("DSMBOS_202611240516.txt"))
    assert (d.kind, d.issue_key, d.day, d.month) == ("final", "FINAL", 23, 11)
    assert (d.max_f, d.max_time_local, d.min_f, d.min_time_local) == (69, "14:01", 48, "23:59")
    assert d.precip_in == Decimal("0.78")
    assert (d.wind.dir_deg, d.wind.speed_mph) == (40, 22)
    assert (d.gust.dir_deg, d.gust.speed_mph, d.gust.time_local) == (300, 32, "15:50")


def test_trace_precipitation() -> None:
    d = parse_dsm(iem("DSMSEA_202611230816.txt"))
    assert d.precip_trace is True
    assert d.precip_in is None


def test_correction_from_nws_api() -> None:
    text = (
        "KNYC DS COR 19/11 641502/ 460700// 64/ 46//0312359/00/00/\n"
        "00/00/20/23062319/\n24112313/N/NN/00/0/NN/EW\n"
    )
    d = parse_dsm(text)
    assert d.is_correction is True
    assert (d.kind, d.day, d.month, d.max_f, d.min_f) == ("final", 19, 11, 64, 46)


def test_wmo_header_and_pil_lines_are_skipped() -> None:
    d = parse_dsm(product_text("nws_dsm/" + NWS[0]))
    assert d.station is not None


def test_unknown_groups_are_errors_not_guesses() -> None:
    d = parse_dsm("KXYZ DS 23/11 M051200/ M102359// 1/ 1//0000000/XX/=")
    assert d.max_f is None
    assert d.min_f is None
    assert any("max group" in e for e in d.errors)
    assert any("precipitation total" in e for e in d.errors)
    assert parse_dsm("garbage").errors == ["no 'KXXX DS' line"]
    big = parse_dsm("KLGA DS 23/11 701335/ 522359// 70/ 58//9780347/125/00/33231645/ 33311644=")
    assert big.precip_in is None
    assert any("precipitation total '125'" in e for e in big.errors)


def test_climate_date_year_from_issue_time() -> None:
    d = parse_dsm("KLGA DS 31/12 510048/ 440659// 1/ 1//0/00/=")
    assert climate_date_for(d, datetime(2027, 1, 1, 5, 16, tzinfo=UTC)) == date(2026, 12, 31)
    d2 = parse_dsm(iem("DSMLGA_202611241216.txt"))
    assert climate_date_for(d2, datetime(2026, 11, 24, 12, 16, tzinfo=UTC)) == date(2026, 11, 24)
