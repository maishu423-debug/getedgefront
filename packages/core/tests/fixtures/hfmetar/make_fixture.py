"""Crop real MADIS HFMETAR files to EdgeFront's stations (v2 Phase 9 B2 fixture).

    uv run python -I packages/core/tests/fixtures/hfmetar/make_fixture.py <src.gz>... <out_dir>

Keeps only our registry stations and the variables the ingest reads, in the same netCDF-3
layout (names, types, units, fill values), gzip-compressed like the originals.
"""

from __future__ import annotations

import gzip
import io
import sys
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file

OURS = {
    "KNYC",
    "KLGA",
    "KBOS",
    "KPHL",
    "KDCA",
    "KATL",
    "KCLT",
    "KJAX",
    "KMIA",
    "KDTW",
    "KMDW",
    "KORD",
    "KMSP",
    "KBNA",
    "KSDF",
    "KAUS",
    "KSAT",
    "KHOU",
    "KDAL",
    "KDFW",
    "KOKC",
    "KDEN",
    "KBKF",
    "KPHX",
    "KLAS",
    "KLAX",
    "KSFO",
    "KSEA",
}
VALUES = ["temperature", "dewpoint", "altimeter", "windDir", "windSpeed", "windGust",
          "visibility", "precipAccum"]  # fmt: skip
KEEP = ["stationId", "dataProvider", "observationTime", "receivedTime", "reportTime"] + [
    f"{v}{s}" for v in VALUES for s in ("", "DD", "QCA", "QCR")
]


def crop(src: Path, dst: Path) -> int:
    nc = netcdf_file(io.BytesIO(gzip.decompress(src.read_bytes())), mmap=False)
    v = nc.variables
    sid = ["".join(c.decode() for c in r).strip("\x00").strip() for r in v["stationId"][:]]
    rows = np.array([i for i, s in enumerate(sid) if s in OURS], dtype=int)
    buf = io.BytesIO()
    out = netcdf_file(buf, "w", version=1)
    for k, val in nc._attributes.items():
        setattr(out, k, val)
    out.cropped = b"EdgeFront test fixture: registry stations and ingest variables only"
    for name in KEEP:
        if name not in v:
            continue
        var = v[name]
        for d in var.dimensions:
            if d not in out.dimensions:
                out.createDimension(d, None if d == "recNum" else nc.dimensions[d])
        o = out.createVariable(name, var.typecode(), var.dimensions)
        for k, val in var._attributes.items():
            setattr(o, k, val)
        data = var[:]
        o[: len(rows)] = data[rows] if var.dimensions and var.dimensions[0] == "recNum" else data
    out.flush()
    raw = buf.getvalue()
    out.close()
    dst.write_bytes(gzip.compress(raw, mtime=0))
    return len(rows)


if __name__ == "__main__":
    *srcs, out_dir = sys.argv[1:]
    for s in srcs:
        src = Path(s)
        name = src.name.replace(".a.gz", ".gz").replace(".b.gz", ".v2.gz")
        n = crop(src, Path(out_dir) / name)
        print(f"{name}: {n} records, {(Path(out_dir) / name).stat().st_size} bytes")
