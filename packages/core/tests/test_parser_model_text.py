"""NBH / NBS / MAV / LAV / PFM decoders, driven by the real fixtures (see fixtures READMEs)."""

from __future__ import annotations

import itertools
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from edgefront_core.parsers.model_text import (
    TextDecodeError,
    decode_block,
    decode_bulletin,
    split_blocks,
)
from edgefront_core.parsers.pfm import PfmDecodeError, decode_point, find_block
from edgefront_core.registry import load_registry

FIX = Path(__file__).parent / "fixtures"
TEXT = sorted((FIX / "nomads_text").glob("*.txt"))
IDS = [s.id for s in load_registry()]


def _bulletin(name: str) -> str:
    return (FIX / "nomads_text" / name).read_text(encoding="ascii")


def _pfm(name: str) -> str:
    return json.loads((FIX / "nws_pfm" / name).read_text(encoding="utf-8"))["productText"]


def z(d: int, h: int) -> datetime:
    return datetime(2026, 11, d, h, tzinfo=UTC)


def first(g, variable):
    return g.series(variable)[0]


@pytest.mark.parametrize("path", TEXT, ids=lambda p: p.name)
def test_every_fixture_decodes_all_registry_stations_cleanly(path: Path) -> None:
    decoded, errors = decode_bulletin(path.read_text(encoding="ascii"), IDS)
    assert errors == {}
    assert sorted(decoded) == sorted(IDS)
    for g in decoded.values():
        assert g.decode_errors == []
        assert g.series("temp")
        assert g.series("dewpt")
        assert g.series("wind")
        assert g.series("cloud")
        times = [v.valid_time for v in g.series("temp")]
        assert times == sorted(set(times))  # strictly increasing, no duplicates
        assert times[0] > g.cycle_time


def test_nbh_hourly_values_and_units() -> None:
    d, _ = decode_bulletin(_bulletin("nbh_2026112513.txt"), ["KDFW", "KMIA"])
    g = d["KDFW"]
    assert (g.product, g.cycle_time) == ("nbh", z(25, 13))
    t = g.series("temp")
    assert len(t) == 25
    assert t[0].valid_time == z(25, 14)
    assert t[-1].valid_time == z(26, 14)
    assert (t[0].value, t[0].native_unit) == (36.0, "degF")
    assert first(g, "dewpt").value == 34.0
    assert (first(g, "wind").value, first(g, "wind").native_unit) == (9.0, "kt")
    sky = first(d["KMIA"], "cloud")
    assert (sky.value, sky.native_unit, sky.category) == (90.0, "pct", None)


def test_nbs_uses_fhr_and_crosses_month_dates() -> None:
    d, _ = decode_bulletin(_bulletin("nbs_2026112513.txt"), ["KDFW"])
    t = d["KDFW"].series("temp")
    # FHR 05 -> 18Z, 3-hourly to FHR 71 -> 28th 12Z
    assert t[0].valid_time == z(25, 18)
    assert t[0].value == 47.0
    assert t[-1].valid_time == z(28, 12)
    assert len(t) == 23
    steps = {(b.valid_time - a.valid_time).total_seconds() for a, b in itertools.pairwise(t)}
    assert steps == {10800}


def test_mav_three_then_six_hourly_categorical_cloud() -> None:
    d, _ = decode_bulletin(_bulletin("mav_2026112506.txt"), ["KDFW", "KMIA"])
    g = d["KDFW"]
    t = g.series("temp")
    assert t[0].valid_time == z(25, 12)
    assert t[0].value == 36.0
    # last three columns are 6-hourly: 18Z, 00Z, 06Z
    assert [v.valid_time for v in t[-3:]] == [z(27, 18), z(28, 0), z(28, 6)]
    c = first(d["KMIA"], "cloud")
    assert (c.value, c.native_unit, c.category) == (None, "category", "OV")
    assert first(g, "wind").value == 8.0


def test_lav_full_bulletin_is_hourly_25h() -> None:
    d, _ = decode_bulletin(_bulletin("lav_202611251330.txt"), ["KDFW", "KNYC"])
    g = d["KDFW"]
    assert g.cycle_time == datetime(2026, 11, 25, 13, 30, tzinfo=UTC)
    t = g.series("temp")
    assert len(t) == 25
    assert t[0].valid_time == z(25, 14)
    assert t[0].value == 35.0
    assert first(d["KNYC"], "cloud").category == "FW"


def test_cells_that_touch_are_split_by_position() -> None:
    # NBH rows like 'CIG -88-88...' and 'VIS 100100...' are fixed width; the splitter must
    # keep working on them even though we don't decode those rows.
    blocks = split_blocks(_bulletin("nbh_2026112513.txt"))
    vis = next(ln for ln in blocks["KDFW"] if ln.startswith(" VIS"))
    assert "100100" in vis
    assert decode_block(blocks["KDFW"]).decode_errors == []


def test_dt_row_mismatch_is_an_error() -> None:
    lines = split_blocks(_bulletin("mav_2026112506.txt"))["KDFW"]
    bad = [ln.replace("/NOV  26", "/NOV  27") if ln.startswith(" DT") else ln for ln in lines]
    with pytest.raises(TextDecodeError, match="DT row"):
        decode_block(bad)


def test_unexpected_cell_is_recorded_not_guessed() -> None:
    lines = split_blocks(_bulletin("lav_202611251330.txt"))["KDFW"]
    bad = [ln[:5] + " XX" + ln[8:] if ln.startswith(" TMP") else ln for ln in lines]
    g = decode_block(bad)
    assert g.decode_errors == ["TMP 25/14Z: 'XX'"]
    assert g.series("temp")[0].valid_time == z(25, 15)  # the bad cell is skipped, not filled


# ---------------------------------------------------------------- PFM


def test_pfm_okx_point_block() -> None:
    fc = decode_point(find_block(_pfm("PFMOKX_202611250950.json"), "Central Park-New York NY"))
    assert (fc.lat, fc.lon, fc.elev_ft) == (40.78, -73.97, 16)
    assert fc.issued_at == datetime(2026, 11, 25, 9, 50, tzinfo=UTC)
    assert fc.decode_errors == []
    t = fc.series("temp")
    assert t[0].valid_time == z(25, 12)
    assert t[0].value == 36.0
    assert t[0].native_unit == "degF"
    assert first(fc, "rh").value == 54.0  # the product's own RH
    w = first(fc, "wind")
    assert (w.value, w.native_unit) == (5.0, "mph")
    assert first(fc, "cloud").category == "FW"
    assert {c.category for c in fc.series("cloud")} >= {"B1", "B2"}


def test_pfm_grid_box_latlon_and_columns_before_issue() -> None:
    # VEF: 'Elev. (Average Over 2.5KM Grid Box): 2181 ft'; issued 10:32 PM PST, the matrix
    # starts at 1 PM the same day with blank cells until 09Z.
    fc = decode_point(find_block(_pfm("PFMVEF_202611250632.json"), "Las Vegas-Clark NV"))
    assert (fc.lat, fc.lon, fc.elev_ft) == (36.07, -115.16, 2181)
    assert fc.issued_at == datetime(2026, 11, 25, 6, 32, tzinfo=UTC)
    t = fc.series("temp")
    assert t[0].valid_time == z(25, 9)
    assert t[0].value == 48.0
    assert first(fc, "cloud").category == "B1"


def test_pfm_single_space_latlon_mountain_zone() -> None:
    fc = decode_point(
        find_block(_pfm("PFMBOU_202611250646.json"), "Denver Int'l Airport-Denver CO")
    )
    assert (fc.lat, fc.lon, fc.elev_ft) == (39.83, -104.65, 5379)
    assert first(fc, "temp").valid_time == z(25, 9)


def test_pfm_every_station_block_in_every_fixture_decodes() -> None:
    points = [s.pfm_point for s in load_registry() if s.pfm_point]
    n, found = 0, set()
    for f in sorted((FIX / "nws_pfm").glob("PFM*.json")):
        text = _pfm(f.name)
        for point in points:
            block = find_block(text, point)
            if block is None:
                continue
            fc = decode_point(block)
            assert fc.decode_errors == []
            assert len(fc.series("temp")) >= 18
            n += 1
            found.add(point)
    assert n >= 35
    assert found == set(points)  # every registry PFM point (26) is covered by a fixture


def test_pfm_missing_point_and_inconsistent_hours() -> None:
    text = _pfm("PFMFWD_202611251107.json")
    assert find_block(text, "Dallas Hobby-Dallas TX") is None
    block = find_block(text, "DFW Airport-Dallas TX")
    assert block is not None
    bad = [ln.replace("UTC 3hrly     09", "UTC 3hrly     10") for ln in block]
    with pytest.raises(PfmDecodeError, match="UTC row"):
        decode_point(bad)
