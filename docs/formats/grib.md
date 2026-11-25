# GRIB2 models (GFS, IFS, AIFS): format note

Code: `services/worker/src/edgefront_worker/grib/` (`sources.py` URLs + indexes + byte ranges,
`fields.py` eccodes decoding + nearest land point, `ingest.py` runs). Fixtures:
`services/worker/tests/fixtures/grib/` — real messages, cropped to CONUS (README lists source
URLs, UTC fetch times and full-vs-cropped values). Capture: `uv run python tools/capture_grib_fixtures.py YYYYMMDDHH`.

Verified 2026-11-25 against the live 06Z runs.

## Sources and transfers

| Model | Files | Index | Steps used | Cycles |
|---|---|---|---|---|
| **GFS** 0.25° | AWS `https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.YYYYMMDD/HH/atmos/gfs.tHHz.pgrb2.0p25.fFFF`, fallback NOMADS `…/gfs/prod/…` (same path) | wgrib2 `.idx` (`n:offset:d=YYYYMMDDHH:VAR:LEVEL:FCST:`) | f000–f054 hourly (55) | 00/06/12/18 |
| **IFS** 0.25° | `https://data.ecmwf.int/forecasts/YYYYMMDD/HHz/ifs/0p25/oper/YYYYMMDDHH0000-{step}h-oper-fc.grib2` | `.index` JSON lines (`param`, `levtype`, `_offset`, `_length`) | 0–54 every 3 h (19) | 00/06/12/18 (06/18 use the `oper` stream too) |
| **AIFS** (single) 0.25° | same layout with `aifs-single` | same | 0–54 every 6 h (10) | 00/06/12/18 |

- One HTTP `Range` request per message; a response must be 206, the exact length, and start with
  `GRIB`. Every request uses EdgeFront's client (EdgeFront User-Agent with contact).
- **Deviation from the Phase 5 brief:** Herbie and `ecmwf-opendata` were installed and used
  to *verify* the URL layout (ecmwf-opendata builds exactly the URLs above), but their download
  paths send the default `python-requests` User-Agent, and Herbie also probes a third-party
  mirror (`pando-rgw01.chpc.utah.edu`) when it looks for files. That conflicts with owner A2 ("Don't
  hide our identity from any upstream"), so EdgeFront does the idx/index lookup and byte
  ranges itself (~150 lines, `sources.py`).
- Timing seen: GFS 06Z f006 `.idx` on NOMADS at 09:29:39Z, on AWS at 09:45:53Z (AWS ~16 min
  later); a step missing on AWS is taken from NOMADS. IFS/AIFS 06Z were complete by 15:19Z.

## Fields

| Our variable | GFS (idx match, exact) | IFS / AIFS (`param`, `levtype=sfc`) | Native unit (from the message's `units` key) |
|---|---|---|---|
| temp | `:TMP:2 m above ground:{F}:` | `2t` | K |
| dewpt | `:DPT:2 m above ground:{F}:` | `2d` | K |
| rh | `:RH:2 m above ground:{F}:` (**own**) | — (computed from T/Td, flagged) | % |
| wind | `:UGRD:` / `:VGRD:10 m above ground:{F}:` → speed √(u²+v²) | `10u` / `10v` → speed | m s⁻¹ → kt |
| cloud | `:TCDC:entire atmosphere:{F}:` (instantaneous; **not** `0-6 hour ave fcst`) | `tcc` | GFS `%`; **IFS `(0 - 1)`**; **AIFS `%`** |
| land-sea mask | `:LAND:surface:anl:` (f000) | `lsm` (step 0) | (0 - 1) |
| orography | `:HGT:surface:anl:` (gpm) | `z` (step 0, m² s⁻² ÷ g) | m |

`{F}` is `anl` at f000, else `N hour fcst`. IFS and AIFS encode total cloud differently
(IFS paramId 164, fraction; AIFS paramId 228164, percent) — the decoder reads the `units` key of
every message and refuses units it does not know.

Each message is checked: `dataDate`/`dataTime` must equal the run and `stepRange` the step,
otherwise the run fails (tested by serving 06Z data under 12Z URLs).

## Grid point (space rule)

Grids are regular 0.25° lat/lon (GFS lon 0…359.75, ECMWF −180…179.75, both north→south). For
each station: among the grid points within 4 cells, the **nearest point whose land fraction is
≥ 0.5** in the run's own land-sea mask; if none, the nearest point with `is_land = false`
(reason stored). Stored per run and station: grid lat/lon, great-circle distance, land fraction,
model surface height. No interpolation, no lapse-rate or bias adjustment.

## Runs

A run is created when its step 0 is published; each later step is stored as soon as it appears
(`status = partial`, `steps_fetched` / `steps_expected`), `complete` when all steps are in.
Steps already stored are never downloaded again (kept in `model_runs.notes`). Latest 4 runs per
model are kept.
