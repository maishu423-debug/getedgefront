"""METAR parser tests, all on real reports saved from aviationweather.gov (see fixtures README)."""

from __future__ import annotations

import glob
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from core_fixtures import FIXTURES, load_json

from edgefront_core.parsers.metar import (
    MetarParseError,
    parse_metar,
    resolve_observed_at,
    synoptic_hour,
)

BATCHES = sorted(glob.glob(str(FIXTURES / "aviationweather" / "metar_36h_batch*.json")))


def _all_reports() -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for path in BATCHES:
        out += load_json("aviationweather/" + path.replace("\\", "/").rsplit("/", 1)[1])
    return out


def _r1(v: object) -> float | None:
    return None if v is None else round(float(v), 1)  # type: ignore[arg-type]


def test_corpus_matches_aviationweather_decoding() -> None:
    """Every real report decodes to the same values aviationweather.gov publishes."""
    reports = _all_reports()
    assert len(reports) > 1000
    for x in reports:
        raw = str(x["rawOb"])
        m = parse_metar(raw)
        ref = datetime.fromtimestamp(int(x["obsTime"]), UTC)  # type: ignore[call-overload]
        assert resolve_observed_at(m, ref) == ref, raw
        assert m.report_type == x["metarType"], raw
        assert _r1(m.temp_c) == _r1(x.get("temp")), raw
        assert _r1(m.dewpt_c) == _r1(x.get("dewp")), raw
        assert ("VRB" if m.wind_vrb else m.wind_dir_deg) == x.get("wdir"), raw
        assert m.wind_kt == x.get("wspd"), raw
        assert m.gust_kt == x.get("wgst"), raw
        assert _r1(m.slp_hpa) == _r1(x.get("slp")), raw
        assert _r1(m.max6h_c) == _r1(x.get("maxT")), raw
        assert _r1(m.min6h_c) == _r1(x.get("minT")), raw
        assert _r1(m.max24h_c) == _r1(x.get("maxT24")), raw
        assert _r1(m.min24h_c) == _r1(x.get("minT24")), raw
        if m.altim_inhg is not None:
            # aviationweather publishes hPa; allow its rounding (±1 hPa).
            assert abs(float(m.altim_inhg) * 33.8639 - float(x["altim"])) <= 1.0, raw  # type: ignore[arg-type]


def test_metar_with_t_group_prefers_tenths() -> None:
    m = parse_metar(
        "METAR KJAX 241556Z 02010KT 10SM SCT015 BKN160 BKN250 20/16 A3009 RMK AO2 SLP189 "
        "T02000161 $"
    )
    assert (m.report_type, m.station, m.day, m.hour, m.minute) == ("METAR", "KJAX", 24, 15, 56)
    assert (m.temp_c, m.dewpt_c, m.temp_precision) == (Decimal("20.0"), Decimal("16.1"), "tenths")
    assert (m.wind_dir_deg, m.wind_kt, m.gust_kt, m.wind_vrb) == (20, 10, None, False)
    assert m.vis_mi == Decimal(10)
    assert [(s.cover, s.base_ft) for s in m.sky] == [("SCT", 1500), ("BKN", 16000), ("BKN", 25000)]
    assert m.altim_inhg == Decimal("30.09")
    assert m.slp_hpa == Decimal("1018.9")


def test_speci_without_t_group_uses_whole_degrees() -> None:
    m = parse_metar("SPECI KPHL 231148Z 23008KT 4SM BR BKN004 OVC060 14/13 A2988 RMK AO2 $")
    assert m.report_type == "SPECI"
    assert (m.temp_c, m.dewpt_c, m.temp_precision) == (Decimal(14), Decimal(13), "whole")
    assert m.unparsed == ["BR"]


def test_cor_flag() -> None:
    m = parse_metar(
        "METAR KLGA 241251Z COR 33016G23KT 10SM FEW040 FEW110 07/M02 A3031 RMK AO2 "
        "PK WND 30026/1215 SLP262 T00671017 $"
    )
    assert m.is_correction is True
    assert (m.wind_dir_deg, m.wind_kt, m.gust_kt) == (330, 16, 23)
    assert (m.temp_c, m.dewpt_c) == (Decimal("6.7"), Decimal("-1.7"))


def test_vrb_wind_with_gust() -> None:
    m = parse_metar(
        "METAR KNYC 241551Z AUTO VRB03G18KT 10SM CLR 08/M04 A3038 RMK AO2 SLP280 T00831044 $"
    )
    assert m.is_auto is True
    assert (m.wind_vrb, m.wind_dir_deg, m.wind_kt, m.gust_kt) == (True, None, 3, 18)
    assert [(s.cover, s.base_ft) for s in m.sky] == [("CLR", None)]


def test_missing_wind_group_is_none_not_zero() -> None:
    m = parse_metar(
        "METAR KNYC 241451Z AUTO 10SM CLR 07/M04 A3038 RMK AO2 SLP278 T00671044 51030 $"
    )
    assert (m.wind_dir_deg, m.wind_kt, m.gust_kt, m.wind_vrb) == (None, None, None, False)


def test_negative_temperatures() -> None:
    m = parse_metar("METAR KDTW 241253Z 32004KT 10SM FEW035 M04/M08 A3055 RMK AO2 SLP354 T10441078")
    assert (m.temp_c, m.dewpt_c) == (Decimal("-4.4"), Decimal("-7.8"))


def test_six_hour_groups_at_synoptic_report() -> None:
    m = parse_metar(
        "METAR KBOS 241154Z 31009KT 10SM FEW045 FEW110 06/M02 A3016 RMK AO2 SLP214 T00561017 "
        "10089 20056 53034"
    )
    assert (m.max6h_c, m.min6h_c) == (Decimal("8.9"), Decimal("5.6"))
    assert m.max24h_c is None


def test_twenty_four_hour_group_at_lst_midnight() -> None:
    m = parse_metar(
        "METAR KBOS 240454Z 29011KT 10SM FEW060 09/M01 A3000 RMK AO2 SLP158 T00891006 402060089"
    )
    assert (m.max24h_c, m.min24h_c) == (Decimal("20.6"), Decimal("8.9"))


def test_fractional_visibility() -> None:
    m = parse_metar("SPECI KPHL 231234Z 24007KT 1 1/4SM BR OVC002 14/13 A2989 RMK AO2 T01390133 $")
    assert m.vis_mi == Decimal("1.25")
    m2 = parse_metar("SPECI KPHL 231334Z 24009KT 2 1/2SM BR OVC003 14/13 A2991 RMK AO2 T01390133 $")
    assert m2.vis_mi == Decimal("2.50")


def test_slpno_and_wind_variation() -> None:
    m = parse_metar(
        "METAR KSDF 231256Z 36010KT 10SM FEW018 FEW075 05/02 A3019 RMK AO2 SLPNO T00500022"
    )
    assert m.slp_hpa is None
    v = parse_metar(
        "METAR KNYC 232151Z AUTO 30009G17KT 270V330 10SM OVC047 15/08 A2996 RMK AO2 SLP136 "
        "T01500083 $"
    )
    assert (v.wind_dir_deg, v.wind_kt, v.gust_kt) == (300, 9, 17)
    assert v.unparsed == []


def test_missing_temperature_entirely() -> None:
    m = parse_metar("METAR KXYZ 241553Z 18005KT 10SM CLR A3001 RMK AO2")
    assert (m.temp_c, m.dewpt_c, m.temp_precision) == (None, None, None)


def test_temperature_without_dewpoint() -> None:
    m = parse_metar("METAR KXYZ 241553Z 18005KT 10SM CLR M05/ A3001 RMK AO2")
    assert (m.temp_c, m.dewpt_c) == (Decimal(-5), None)


def test_garbage_raises() -> None:
    with pytest.raises(MetarParseError):
        parse_metar("NIL")


def test_resolve_observed_at_month_rollover() -> None:
    m = parse_metar("METAR KNYC 302351Z 00000KT 10SM CLR 01/M01 A3000 RMK AO2")
    # Fetched on Dec 1 00:05Z → the report is from Nov 30.
    assert resolve_observed_at(m, datetime(2026, 12, 1, 0, 5, tzinfo=UTC)) == datetime(
        2026, 11, 30, 23, 51, tzinfo=UTC
    )


@pytest.mark.parametrize(
    ("obs", "expected"),
    [
        (datetime(2026, 11, 24, 11, 54, tzinfo=UTC), datetime(2026, 11, 24, 12, tzinfo=UTC)),
        (datetime(2026, 11, 23, 23, 51, tzinfo=UTC), datetime(2026, 11, 24, 0, tzinfo=UTC)),
        (datetime(2026, 11, 24, 10, 53, tzinfo=UTC), None),
    ],
)
def test_synoptic_hour(obs: datetime, expected: datetime | None) -> None:
    assert synoptic_hour(obs) == expected
