from __future__ import annotations

import pytest
from core_fixtures import load_json, product_text

from edgefront_core.parsers.stations import (
    PfmPoint,
    dsm_station_id,
    match_pfm_point,
    parse_awc_stationinfo,
    parse_nws_points,
    parse_nws_station,
    parse_pfm_points,
    points_url,
)


def test_awc_stationinfo_all_28() -> None:
    st = parse_awc_stationinfo(load_json("aviationweather/stationinfo_28.json"))
    assert len(st) == 28
    atl = st["KATL"]
    assert atl.site == "Atlanta/Hartsfield-Jackson Intl"
    assert atl.lat == pytest.approx(33.62972)
    assert atl.lon == pytest.approx(-84.44223)
    assert atl.elev_m == 309
    assert atl.state == "GA"


def test_awc_stationinfo_rejects_non_list() -> None:
    with pytest.raises(ValueError, match="expected a JSON list"):
        parse_awc_stationinfo({"error": "x"})


def test_nws_station_knyc() -> None:
    s = parse_nws_station(load_json("nws/station_KNYC.json"))
    assert s.icao == "KNYC"
    assert s.name == "New York City, Central Park"
    assert s.tz == "America/New_York"
    assert s.lat == pytest.approx(40.78333)
    assert s.lon == pytest.approx(-73.96667)
    assert s.elevation_m == pytest.approx(46.9392)


def test_nws_station_kdfw() -> None:
    s = parse_nws_station(load_json("nws/station_KDFW.json"))
    assert s.icao == "KDFW"
    assert s.tz == "America/Chicago"
    assert s.lat is not None
    assert 32 < s.lat < 33.5


def test_nws_points_knyc() -> None:
    p = parse_nws_points(load_json("nws/points_40.7833_-73.9667.json"))
    assert (p.office, p.grid_x, p.grid_y, p.cwa) == ("OKX", 34, 45, "OKX")
    assert p.tz == "America/New_York"


def test_points_url_uses_four_decimals() -> None:
    assert points_url(40.78333, -73.96667) == "https://api.weather.gov/points/40.7833,-73.9667"


@pytest.mark.parametrize(
    ("fixture", "icao"),
    [
        ("nws_products/dsm_NYC_797f72b6.json", "KNYC"),
        ("nws_products/dsm_MSP_a248e09c.json", "KMSP"),
        ("nws_products/dsm_SAT_36343880.json", "KSAT"),
    ],
)
def test_dsm_station_id_from_real_products(fixture: str, icao: str) -> None:
    assert dsm_station_id(product_text(fixture)) == icao


def test_dsm_station_id_none_for_other_text() -> None:
    assert dsm_station_id("\n000\nCXUS41 KOKX 240530\nDSMNYC\n\n") is None


def test_pfm_points_okx() -> None:
    pts = parse_pfm_points(product_text("nws_products/pfm_OKX_ad398d3d.json"))
    names = [p.name for p in pts]
    assert len(pts) == 15
    assert names[0] == "Central Park-New York NY"
    assert "LaGuardia Airport-Queens NY" in names
    cp = pts[0]
    assert (cp.ugc, cp.lat, cp.lon, cp.elev_ft) == ("NYZ072-242100-", 40.78, -73.97, 16)
    # Zone codes repeat within one product, so the name is the key.
    assert sum(1 for p in pts if p.ugc.startswith("NYZ080")) == 2


def test_pfm_points_vef_grid_box_elevation_format() -> None:
    pts = parse_pfm_points(product_text("nws_products/pfm_VEF_bf0c124f.json"))
    assert len(pts) == 20
    lv = pts[0]
    assert (lv.ugc, lv.name, lv.lat, lv.lon, lv.elev_ft) == (
        "NVZ020-250000-",
        "Las Vegas-Clark NV",
        36.07,
        -115.16,
        2181,
    )
    death_valley = next(p for p in pts if p.name == "Death Valley-Inyo CA")
    assert death_valley.elev_ft == -184
    m = match_pfm_point(pts, 36.07188, -115.1634)  # KLAS
    assert m.point is not None
    assert m.point.name == "Las Vegas-Clark NV"


def test_match_pfm_central_park() -> None:
    pts = parse_pfm_points(product_text("nws_products/pfm_OKX_ad398d3d.json"))
    m = match_pfm_point(pts, 40.78333, -73.96667)
    assert m.point is not None
    assert m.point.name == "Central Park-New York NY"
    assert m.distance_km is not None
    assert m.distance_km < 1


def test_match_pfm_too_far() -> None:
    pts = parse_pfm_points(product_text("nws_products/pfm_OKX_ad398d3d.json"))
    m = match_pfm_point(pts, 39.87, -75.24)  # Philadelphia: not in the OKX PFM
    assert m.point is None
    assert "km away" in m.reason


def test_match_pfm_ambiguous() -> None:
    pts = [
        PfmPoint("XXZ001-", "A", 40.00, -75.00, None),
        PfmPoint("XXZ002-", "B", 40.01, -75.00, None),
    ]
    m = match_pfm_point(pts, 40.005, -75.0)
    assert m.point is None
    assert m.reason.startswith("ambiguous")
