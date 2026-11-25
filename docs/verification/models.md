# Model spot checks and GRIB memory (Phase 5)

Run 2026-11-25 ~15:45Z with `tools/spot_check_models.py` against the runs stored by the live
ingest (GFS/IFS/AIFS 06Z, NBM 14Z, GFS-MOS 06Z, LAMP 14:30Z, PFM latest per office). Each
stored value is compared with an **independent reading** of the upstream data:

| Model | Reference | Why it is independent |
|---|---|---|
| GFS | NOMADS GRIB filter (`filter_gfs_0p25.pl`, server-side wgrib2 subset of the same cycle/step, a 1° box), decoded with eccodes, value at the stored grid lat/lon | different server (NOMADS, not AWS), different file (wgrib2 re-encodes the subset), different grid indexing (1° box) |
| IFS, AIFS | the full `2t` field downloaded again and opened with **cfgrib + xarray**, `.sel(latitude, longitude)` at the stored grid point | second decoding library and coordinate handling (xarray), not our eccodes/index code |
| NBM, GFS-MOS, LAMP | the raw NOMADS bulletin downloaded again; the station's `TMP` row split on whitespace | not the fixed-width column decoder |
| PFM | the raw `productText` from api.weather.gov; the point block's `Temp` row split on whitespace | not the position-based decoder |

Native units: K for GRIB temperatures, °F for text products. Tolerance: 0.05 K (GRIB), exact (text).

**Result: 82 checks, 0 mismatches.**

| Model | Station | Run | Valid | Stored (native) | Reference | Diff | Reference method | |
|---|---|---|---|---|---|---|---|---|
| GFS | KDFW | 11-25 06Z | 11-25 12Z | 276.19 | 276.19 | +0.00 K | NOMADS GRIB filter (wgrib2 subset) + eccodes | ✅ |
| GFS | KDFW | 11-25 06Z | 11-26 06Z | 278.05 | 278.05 | +0.00 K | NOMADS GRIB filter (wgrib2 subset) + eccodes | ✅ |
| GFS | KNYC | 11-25 06Z | 11-25 12Z | 276.81 | 276.81 | +0.00 K | NOMADS GRIB filter (wgrib2 subset) + eccodes | ✅ |
| GFS | KNYC | 11-25 06Z | 11-26 06Z | 280.88 | 280.88 | +0.00 K | NOMADS GRIB filter (wgrib2 subset) + eccodes | ✅ |
| GFS | KMIA | 11-25 06Z | 11-25 12Z | 295.76 | 295.76 | +0.00 K | NOMADS GRIB filter (wgrib2 subset) + eccodes | ✅ |
| GFS | KMIA | 11-25 06Z | 11-26 06Z | 294.48 | 294.48 | +0.00 K | NOMADS GRIB filter (wgrib2 subset) + eccodes | ✅ |
| GFS | KDEN | 11-25 06Z | 11-25 12Z | 272.06 | 272.06 | +0.00 K | NOMADS GRIB filter (wgrib2 subset) + eccodes | ✅ |
| GFS | KDEN | 11-25 06Z | 11-26 06Z | 274.99 | 274.99 | +0.00 K | NOMADS GRIB filter (wgrib2 subset) + eccodes | ✅ |
| IFS | KDFW | 11-25 06Z | 11-25 12Z | 276.17 | 276.17 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| IFS | KNYC | 11-25 06Z | 11-25 12Z | 273.17 | 273.17 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| IFS | KMIA | 11-25 06Z | 11-25 12Z | 294.67 | 294.67 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| IFS | KDEN | 11-25 06Z | 11-25 12Z | 272.17 | 272.17 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| IFS | KSEA | 11-25 06Z | 11-25 12Z | 283.67 | 283.67 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| IFS | KDFW | 11-25 06Z | 11-26 06Z | 278.59 | 278.59 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| IFS | KNYC | 11-25 06Z | 11-26 06Z | 279.09 | 279.09 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| IFS | KMIA | 11-25 06Z | 11-26 06Z | 293.84 | 293.84 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| IFS | KDEN | 11-25 06Z | 11-26 06Z | 274.09 | 274.09 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| IFS | KSEA | 11-25 06Z | 11-26 06Z | 283.09 | 283.09 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| AIFS | KDFW | 11-25 06Z | 11-25 12Z | 274.57 | 274.57 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| AIFS | KNYC | 11-25 06Z | 11-25 12Z | 273.82 | 273.82 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| AIFS | KMIA | 11-25 06Z | 11-25 12Z | 295.82 | 295.82 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| AIFS | KDEN | 11-25 06Z | 11-25 12Z | 271.57 | 271.57 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| AIFS | KSEA | 11-25 06Z | 11-25 12Z | 283.32 | 283.32 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| AIFS | KDFW | 11-25 06Z | 11-26 06Z | 277.03 | 277.03 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| AIFS | KNYC | 11-25 06Z | 11-26 06Z | 280.03 | 280.03 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| AIFS | KMIA | 11-25 06Z | 11-26 06Z | 295.28 | 295.28 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| AIFS | KDEN | 11-25 06Z | 11-26 06Z | 273.53 | 273.53 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| AIFS | KSEA | 11-25 06Z | 11-26 06Z | 284.28 | 284.28 | +0.00 K | full field, cfgrib + xarray .sel() | ✅ |
| NBM | KDFW | 11-25 14Z | 11-25 15Z | 39.00 | 39.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| NBM | KDFW | 11-25 14Z | 11-25 16Z | 42.00 | 42.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| NBM | KDFW | 11-25 14Z | 11-25 17Z | 45.00 | 45.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| NBM | KNYC | 11-25 14Z | 11-25 15Z | 43.00 | 43.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| NBM | KNYC | 11-25 14Z | 11-25 16Z | 45.00 | 45.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| NBM | KNYC | 11-25 14Z | 11-25 17Z | 46.00 | 46.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| NBM | KMIA | 11-25 14Z | 11-25 15Z | 73.00 | 73.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| NBM | KMIA | 11-25 14Z | 11-25 16Z | 73.00 | 73.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| NBM | KMIA | 11-25 14Z | 11-25 17Z | 73.00 | 73.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| NBM | KDEN | 11-25 14Z | 11-25 15Z | 31.00 | 31.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| NBM | KDEN | 11-25 14Z | 11-25 16Z | 34.00 | 34.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| NBM | KDEN | 11-25 14Z | 11-25 17Z | 38.00 | 38.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| NBM | KSEA | 11-25 14Z | 11-25 15Z | 51.00 | 51.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| NBM | KSEA | 11-25 14Z | 11-25 16Z | 51.00 | 51.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| NBM | KSEA | 11-25 14Z | 11-25 17Z | 52.00 | 52.00 | +0.00 °F | raw NBH bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KDFW | 11-25 06Z | 11-25 12Z | 36.00 | 36.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KDFW | 11-25 06Z | 11-25 15Z | 39.00 | 39.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KDFW | 11-25 06Z | 11-25 18Z | 49.00 | 49.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KNYC | 11-25 06Z | 11-25 12Z | 35.00 | 35.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KNYC | 11-25 06Z | 11-25 15Z | 39.00 | 39.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KNYC | 11-25 06Z | 11-25 18Z | 43.00 | 43.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KMIA | 11-25 06Z | 11-25 12Z | 71.00 | 71.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KMIA | 11-25 06Z | 11-25 15Z | 73.00 | 73.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KMIA | 11-25 06Z | 11-25 18Z | 74.00 | 74.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KDEN | 11-25 06Z | 11-25 12Z | 27.00 | 27.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KDEN | 11-25 06Z | 11-25 15Z | 31.00 | 31.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KDEN | 11-25 06Z | 11-25 18Z | 46.00 | 46.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KSEA | 11-25 06Z | 11-25 12Z | 54.00 | 54.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KSEA | 11-25 06Z | 11-25 15Z | 54.00 | 54.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| GFS_MOS | KSEA | 11-25 06Z | 11-25 18Z | 57.00 | 57.00 | +0.00 °F | raw MAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KDFW | 11-25 14Z | 11-25 15Z | 38.00 | 38.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KDFW | 11-25 14Z | 11-25 16Z | 42.00 | 42.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KDFW | 11-25 14Z | 11-25 17Z | 44.00 | 44.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KNYC | 11-25 14Z | 11-25 15Z | 40.00 | 40.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KNYC | 11-25 14Z | 11-25 16Z | 42.00 | 42.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KNYC | 11-25 14Z | 11-25 17Z | 43.00 | 43.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KMIA | 11-25 14Z | 11-25 15Z | 73.00 | 73.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KMIA | 11-25 14Z | 11-25 16Z | 74.00 | 74.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KMIA | 11-25 14Z | 11-25 17Z | 74.00 | 74.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KDEN | 11-25 14Z | 11-25 15Z | 29.00 | 29.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KDEN | 11-25 14Z | 11-25 16Z | 36.00 | 36.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KDEN | 11-25 14Z | 11-25 17Z | 40.00 | 40.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KSEA | 11-25 14Z | 11-25 15Z | 57.00 | 57.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KSEA | 11-25 14Z | 11-25 16Z | 57.00 | 57.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| LAMP | KSEA | 11-25 14Z | 11-25 17Z | 57.00 | 57.00 | +0.00 °F | raw LAV bulletin, TMP row split on spaces | ✅ |
| PFM | KDFW | 11-25 11Z | 11-25 12Z | 34.00 | 34.00 | +0.00 °F | raw PFM product text, Temp row split on spaces | ✅ |
| PFM | KDFW | 11-25 11Z | 11-25 15Z | 38.00 | 38.00 | +0.00 °F | raw PFM product text, Temp row split on spaces | ✅ |
| PFM | KDFW | 11-25 11Z | 11-25 18Z | 47.00 | 47.00 | +0.00 °F | raw PFM product text, Temp row split on spaces | ✅ |
| PFM | KNYC | 11-25 10Z | 11-25 12Z | 36.00 | 36.00 | +0.00 °F | raw PFM product text, Temp row split on spaces | ✅ |
| PFM | KNYC | 11-25 10Z | 11-25 15Z | 42.00 | 42.00 | +0.00 °F | raw PFM product text, Temp row split on spaces | ✅ |
| PFM | KNYC | 11-25 10Z | 11-25 18Z | 45.00 | 45.00 | +0.00 °F | raw PFM product text, Temp row split on spaces | ✅ |
| PFM | KSEA | 11-25 09Z | 11-25 12Z | 52.00 | 52.00 | +0.00 °F | raw PFM product text, Temp row split on spaces | ✅ |
| PFM | KSEA | 11-25 09Z | 11-25 15Z | 51.00 | 51.00 | +0.00 °F | raw PFM product text, Temp row split on spaces | ✅ |
| PFM | KSEA | 11-25 09Z | 11-25 18Z | 52.00 | 52.00 | +0.00 °F | raw PFM product text, Temp row split on spaces | ✅ |

82 checks, 0 mismatches.

## GRIB job memory and transfer (owner: peak RSS < 1 GB)

Each model was run once in a fresh process (`tools/run_grib_once.py`, same code as the worker job)
on the dev machine (Windows, peak working set via psutil; on Linux the worker logs VmRSS/VmHWM from
`/proc/self/status` with every run). One message is decoded at a time (one 0.25° field = 1,038,240
float64 ≈ 8 MB), then dropped.

| Job | Cycle | Steps | Downloaded | Requests | Time (this machine) | Peak RSS | RSS after |
|---|---|---|---|---|---|---|---|
| AIFS | 2026-11-25 06Z | 10 (0–54 h, 6-hourly) | 21.9 MB | 64 | 30 s | **141.5 MB** | 120.2 MB |
| IFS | 2026-11-25 06Z | 19 (0–54 h, 3-hourly) | 51.1 MB | 118 | 60 s | **144.7 MB** | 122.6 MB |
| GFS | 2026-11-25 06Z | 55 (0–54 h, hourly) | 291.5 MB | 390 | 947 s | **144.2 MB** | 110.8 MB |

The peak is the whole Python process (interpreter, SQLAlchemy, eccodes), not only the GRIB data.
GFS time is dominated by the dev machine's connection to S3 (~0.3 MB/s); the data per run is
fixed at ~5.3 MB per step (6 fields × ~0.9 MB).
