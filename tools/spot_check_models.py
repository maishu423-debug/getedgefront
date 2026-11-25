# ruff: noqa: E501, S101  (one-off verification script; asserts are its checks)
"""Spot-check stored model values against independent readings of the upstream data.

    DATABASE_URL=... uv run python tools/spot_check_models.py > docs/verification/models_table.md

- GFS: NOMADS GRIB filter (server-side wgrib2 subset of the same cycle/step, a 1° box) decoded
  with eccodes, value at the stored grid lat/lon.
- IFS / AIFS: the whole 2t field downloaded again and opened with cfgrib + xarray (a second
  decoding library), `.sel()` at the stored grid lat/lon.
- NBM / GFS-MOS / LAMP: the raw bulletin downloaded again; the station's TMP row split on
  whitespace (not the fixed-width decoder) and compared with the stored native °F.
- PFM: the raw product text; the point block's Temp row split on whitespace.

Every request uses the EdgeFront User-Agent. Prints a Markdown table.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import xarray as xr
from sqlalchemy import select

from edgefront_core.db import get_engine, make_sessionmaker, session_scope
from edgefront_core.http import get_with_retry, make_client
from edgefront_core.model_text_ingest import nomads_url
from edgefront_core.models import ModelRun, ModelRunStation, ModelValue
from edgefront_core.timeutil import as_utc
from edgefront_worker.grib.fields import decode
from edgefront_worker.grib.sources import Fetcher, ecmwf_url, parse_ecmwf_index

STATIONS = ("KDFW", "KNYC", "KMIA", "KDEN", "KSEA")
ROWS: list[str] = []


def row(model: str, sid: str, cycle: datetime, valid: datetime, ours: float, ref: float,
        method: str, unit: str) -> None:  # fmt: skip
    diff = ours - ref
    ok = "✅" if abs(diff) <= (0.05 if unit == "K" else 0.0) else "❌"
    ROWS.append(
        f"| {model} | {sid} | {cycle:%m-%d %HZ} | {valid:%m-%d %HZ} | {ours:.2f} | {ref:.2f} "
        f"| {diff:+.2f} {unit} | {method} | {ok} |"
    )


def latest(s, model: str) -> ModelRun:
    return (
        s.execute(
            select(ModelRun).where(ModelRun.model == model).order_by(ModelRun.cycle_time.desc())
        )
        .scalars()
        .first()
    )


def stored(s, run: ModelRun, sid: str, var: str) -> list[ModelValue]:
    return list(
        s.execute(
            select(ModelValue).where(ModelValue.run_id == run.id, ModelValue.station_id == sid,
                                     ModelValue.variable == var).order_by(ModelValue.valid_time)
        ).scalars()
    )  # fmt: skip


def main() -> None:
    factory = make_sessionmaker(get_engine())
    with make_client(timeout=90) as c, session_scope(factory) as s:
        fetch = Fetcher(c)
        # ---- GFS via NOMADS GRIB filter
        run = latest(s, "gfs")
        cyc = as_utc(run.cycle_time)
        for sid in STATIONS[:4]:
            rs = s.get(ModelRunStation, (run.id, sid))
            vals = stored(s, run, sid, "temp")
            for v in (vals[6], vals[24]):
                step = int((as_utc(v.valid_time) - cyc).total_seconds() // 3600)
                lon360 = rs.grid_lon % 360
                params = {
                    "dir": f"/gfs.{cyc:%Y%m%d}/{cyc:%H}/atmos",
                    "file": f"gfs.t{cyc:%H}z.pgrb2.0p25.f{step:03d}",
                    "var_TMP": "on", "lev_2_m_above_ground": "on", "subregion": "",
                    "toplat": f"{rs.grid_lat + 0.5}", "bottomlat": f"{rs.grid_lat - 0.5}",
                    "leftlon": f"{lon360 - 0.5}", "rightlon": f"{lon360 + 0.5}",
                }  # fmt: skip
                r = get_with_retry(
                    c, "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl", params=params
                )
                r.raise_for_status()
                f = decode(r.content)
                j, i = f.grid.nearest_ij(rs.grid_lat, rs.grid_lon)
                assert abs(f.grid.lat(j) - rs.grid_lat) < 1e-6
                row("GFS", sid, cyc, as_utc(v.valid_time), v.native_value, float(f.values[j, i]),
                    "NOMADS GRIB filter (wgrib2 subset) + eccodes", "K")  # fmt: skip
        # ---- IFS / AIFS via cfgrib + xarray on the full field
        for model, od in (("ifs", "ifs"), ("aifs", "aifs-single")):
            run = latest(s, model)
            cyc = as_utc(run.cycle_time)
            for step in (6, 24):
                url = ecmwf_url(od, cyc, step)
                refs = parse_ecmwf_index(fetch.text(url.removesuffix(".grib2") + ".index"), url,
                                         with_static=False)  # fmt: skip
                data = fetch.message(refs["temp"])
                with tempfile.TemporaryDirectory() as d:
                    p = Path(d) / "t2m.grib2"
                    p.write_bytes(data)
                    ds = xr.open_dataset(p, engine="cfgrib", backend_kwargs={"indexpath": ""})
                    for sid in STATIONS:
                        rs = s.get(ModelRunStation, (run.id, sid))
                        v = next(x for x in stored(s, run, sid, "temp")
                                 if as_utc(x.valid_time) == cyc + timedelta(hours=step))  # fmt: skip
                        lon = rs.grid_lon if ds.longitude.max() <= 180 else rs.grid_lon % 360
                        ref = float(ds.t2m.sel(latitude=rs.grid_lat, longitude=lon).values)
                        row(model.upper(), sid, cyc, as_utc(v.valid_time), v.native_value, ref,
                            "full field, cfgrib + xarray .sel()", "K")  # fmt: skip
                    ds.close()
        # ---- text bulletins
        for model, prod, label in (("nbm", "nbh", "NBH"), ("gfs_mos", "mav", "MAV"),
                                   ("lamp", "lav", "LAV")):  # fmt: skip
            run = latest(s, model)
            cyc = as_utc(run.cycle_time)
            text = get_with_retry(c, nomads_url(prod, cyc)).text
            for sid in STATIONS:
                i = text.find(f" {sid} ")
                block = text[i : text.find("\n \n", i)].splitlines()
                tmp = next(ln for ln in block if ln.startswith(" TMP")).split()[1:4]
                vals = stored(s, run, sid, "temp")[:3]
                for v, raw in zip(vals, tmp, strict=True):
                    row(model.upper(), sid, cyc, as_utc(v.valid_time), v.native_value, float(raw),
                        f"raw {label} bulletin, TMP row split on spaces", "°F")  # fmt: skip
        # ---- PFM
        for sid in ("KDFW", "KNYC", "KSEA"):
            run, rs = s.execute(
                select(ModelRun, ModelRunStation)
                .join(ModelRunStation, ModelRunStation.run_id == ModelRun.id)
                .where(ModelRun.model == "pfm", ModelRunStation.station_id == sid)
                .order_by(ModelRun.cycle_time.desc())
            ).first()
            doc = json.loads(get_with_retry(c, run.source_url,
                                            headers={"Accept": "application/ld+json"}).text)  # fmt: skip
            lines = doc["productText"].splitlines()
            k = next(n for n, ln in enumerate(lines) if ln.strip() == rs.point_name)
            temp_line = next(ln for ln in lines[k:] if ln.startswith("Temp"))
            raw = temp_line.split()[1:4]
            vals = stored(s, run, sid, "temp")[:3]
            for v, rv in zip(vals, raw, strict=True):
                row("PFM", sid, as_utc(run.cycle_time), as_utc(v.valid_time), v.native_value,
                    float(rv), "raw PFM product text, Temp row split on spaces", "°F")  # fmt: skip
    print(
        "| Model | Station | Run | Valid | Stored (native) | Reference | Diff | Reference method | |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    print("\n".join(ROWS))
    bad = sum("❌" in r for r in ROWS)
    print(f"\n{len(ROWS)} checks, {bad} mismatches.")


if __name__ == "__main__":
    main()
