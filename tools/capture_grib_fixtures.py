"""Capture small, cropped GRIB2 fixtures for the GFS / IFS / AIFS tests.

    uv run python tools/capture_grib_fixtures.py 2026112506

For each model, two steps (0 and one forecast step) of exactly the messages the ingest uses
are downloaded by byte range (EdgeFront User-Agent), cropped to a CONUS box that holds every
registry station (lat 24..50, lon -125..-66) with eccodes, and written as one GRIB2 file per
step plus an index in the upstream's own format with offsets rewritten for the cropped file.

Cropping re-packs the values (same packing type where eccodes can, else simple packing); the
README records the full-grid value at KDFW's chosen grid point next to the cropped one so the
tests can prove the crop changed nothing that matters.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import eccodes
import numpy as np

from edgefront_core.http import make_client
from edgefront_core.timeutil import utcnow
from edgefront_worker.grib.fields import decode
from edgefront_worker.grib.sources import (
    GFS_AWS,
    Fetcher,
    MessageRef,
    ecmwf_url,
    gfs_patterns,
    gfs_url,
    parse_ecmwf_index,
    parse_wgrib_idx,
)

OUT = Path(__file__).resolve().parents[1] / "services" / "worker" / "tests" / "fixtures" / "grib"
BOX = (24.0, 50.0, -125.0, -66.0)  # lat min, lat max, lon min, lon max
KDFW = (32.8998, -97.0403)


def crop(message: bytes) -> tuple[bytes, float]:
    """Cropped message + the full-grid value at KDFW's nearest point (for the README)."""
    full = decode(message)
    g = full.grid
    lat_min, lat_max, lon_min, lon_max = BOX
    j_top = round((lat_max - g.lat0) / g.dlat)
    j_bot = round((lat_min - g.lat0) / g.dlat)
    i_w = round(((lon_min - g.lon0) % 360) / g.dlon)
    i_e = round(((lon_max - g.lon0) % 360) / g.dlon)
    if i_e < i_w:
        raise SystemExit("box crosses the grid seam; not needed for CONUS on these grids")
    sub = full.values[j_top : j_bot + 1, i_w : i_e + 1]
    j, i = g.nearest_ij(*KDFW)
    ref_value = float(full.values[j, i])

    h = eccodes.codes_new_from_message(message)
    try:
        c = eccodes.codes_clone(h)
    finally:
        eccodes.codes_release(h)
    try:
        packing = eccodes.codes_get(c, "packingType")
        if packing == "grid_ccsds":
            eccodes.codes_set(c, "packingType", "grid_simple")  # portable decode everywhere
        lon_w = g.lon0 + i_w * g.dlon
        lon_e = g.lon0 + i_e * g.dlon
        eccodes.codes_set(c, "Ni", sub.shape[1])
        eccodes.codes_set(c, "Nj", sub.shape[0])
        eccodes.codes_set(c, "latitudeOfFirstGridPointInDegrees", g.lat0 + j_top * g.dlat)
        eccodes.codes_set(c, "latitudeOfLastGridPointInDegrees", g.lat0 + j_bot * g.dlat)
        eccodes.codes_set(c, "longitudeOfFirstGridPointInDegrees", lon_w % 360)
        eccodes.codes_set(c, "longitudeOfLastGridPointInDegrees", lon_e % 360)
        eccodes.codes_set_values(c, np.ascontiguousarray(sub).ravel())
        out = bytes(eccodes.codes_get_message(c))
    finally:
        eccodes.codes_release(c)
    return out, ref_value


def save_step(
    name: str, refs: dict[str, MessageRef], fetch: Fetcher, index_lines: dict[str, str], fmt: str
) -> list[str]:
    body = b""
    idx: list[str] = []
    notes: list[str] = []
    for n, key in enumerate(refs, start=1):
        cropped, ref_value = crop(fetch.message(refs[key]))
        if fmt == "wgrib":
            idx.append(f"{n}:{len(body)}:{index_lines[key]}")
        else:
            row = json.loads(index_lines[key])
            row["_offset"], row["_length"] = len(body), len(cropped)
            idx.append(json.dumps(row))
        body += cropped
        check = decode(cropped)
        j, i = check.grid.nearest_ij(*KDFW)
        notes.append(f"{key}: full {ref_value:.4f} / cropped {float(check.values[j, i]):.4f}")
    (OUT / f"{name}.grib2").write_bytes(body)
    (OUT / f"{name}.{'idx' if fmt == 'wgrib' else 'index'}").write_text(
        "\n".join(idx) + "\n", encoding="utf-8", newline="\n"
    )
    return notes


def _row(name: str, url: str, ext: str, fetched: datetime, notes: list[str]) -> str:
    when = fetched.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"| `{name}.grib2` | {url} (+ `{ext}`) | {when} | {'; '.join(notes)} |"


def main() -> None:
    cycle = datetime.strptime(sys.argv[1], "%Y%m%d%H").replace(tzinfo=UTC)
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    with make_client(timeout=60) as client:
        fetch = Fetcher(client)
        for fxx in (0, 6):
            url = gfs_url(GFS_AWS, cycle, fxx)
            fetched = utcnow()
            text = fetch.text(url + ".idx") or ""
            refs = parse_wgrib_idx(text, url, gfs_patterns(fxx))
            lines = {}
            for line in text.splitlines():
                parts = line.split(":", 2)
                for key, pat in gfs_patterns(fxx).items():
                    if len(parts) == 3 and ":" + parts[2].split(":", 1)[1] == pat:
                        lines[key] = parts[2]
            name = f"gfs_{cycle:%Y%m%d%H}_f{fxx:03d}"
            notes = save_step(name, refs, fetch, lines, "wgrib")
            rows.append(_row(name, url, ".idx", fetched, notes))
        for model, od, steps in (("ifs", "ifs", (0, 3)), ("aifs", "aifs-single", (0, 6))):
            for step in steps:
                url = ecmwf_url(od, cycle, step)
                fetched = utcnow()
                text = fetch.text(url.removesuffix(".grib2") + ".index") or ""
                refs = parse_ecmwf_index(text, url, with_static=step == 0)
                lines = {}
                for line in text.splitlines():
                    if line.strip():
                        row = json.loads(line)
                        for key, ref in refs.items():
                            if row.get("_offset") == ref.offset:
                                lines[key] = line
                name = f"{model}_{cycle:%Y%m%d%H}_{step}h"
                notes = save_step(name, refs, fetch, lines, "ecmwf")
                rows.append(_row(name, url, ".index", fetched, notes))
    readme = OUT / "README.md"
    readme.write_text(
        "# Fixtures: grib\n\n"
        "Real GFS (NOAA open data on AWS) and ECMWF open-data IFS / AIFS messages (CC BY 4.0, "
        "© ECMWF), downloaded by byte range with the EdgeFront User-Agent, then **cropped** to "
        f"lat {BOX[0]}..{BOX[1]}, lon {BOX[2]}..{BOX[3]} with eccodes "
        "(`tools/capture_grib_fixtures.py`). Only the messages the ingest reads are kept. "
        "ECMWF CCSDS packing is re-packed as simple packing; GFS keeps its packing type. "
        "The `.idx` / `.index` files are the upstream lines with offsets rewritten for the "
        "cropped file. Last column: value at KDFW's nearest grid point in the full field vs "
        "the cropped fixture.\n\n"
        "| File | Source URL | Fetched (UTC) | Full vs cropped at KDFW |\n|---|---|---|---|\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    total = sum(p.stat().st_size for p in OUT.glob("*.grib2"))
    print(f"saved {len(rows)} step files, {total / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
