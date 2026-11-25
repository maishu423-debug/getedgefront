# NOMADS station text bulletins (NBM NBH/NBS, GFS MOS MAV, GFS LAMP LAV): format note

Decoder: `packages/core/src/edgefront_core/parsers/model_text.py`. Fixtures:
`packages/core/tests/fixtures/nomads_text/` (8 bulletins, 2 cycles per product, fetched
2026-11-25; URL, UTC fetch time and full size in the README). Each fixture keeps only the 28
registry station blocks, byte-for-byte, because the full files are 3.6–29 MB. Capture:
`uv run python tools/capture_model_text.py <nbh|nbs|mav|lav> <cycle>...`.

All 8 bulletins decode for all 28 stations with 0 errors (`tests/test_parser_model_text.py`).

## Where the files are (verified 2026-11-25)

| Product | URL (`https://nomads.ncep.noaa.gov/pub/data/nccf/com/…`) | Cycles | Size | Blocks |
|---|---|---|---|---|
| NBM **NBH** (hourly) | `blend/prod/blend.YYYYMMDD/HH/text/blend_nbhtx.tHHz` | every hour | ~28 MB | 9,576 |
| NBM **NBS** (short range) | `blend/prod/blend.YYYYMMDD/HH/text/blend_nbstx.tHHz` | every hour | ~29 MB | 9,576 |
| GFS MOS **MAV** | `gfs_mos/prod/gfs_mos.YYYYMMDD/mdl_gfsmav.tHHz` | 00, 06, 12, 18 | 3.6 MB | ~2,318 |
| GFS **LAMP** (LAV) | `lmp/prod/lmp.YYYYMMDD/lmp.tHH30z.lavtxt.ascii` | every hour at HH30 | 4.6 MB | 2,313 |

- **LAMP:** the directory has `lmp.tHHMMz.lavtxt.ascii` every 15 min, but only the **HH30** issuance
  is the full bulletin (25 hourly columns with TMP/DPT/WDR/WSP/CLD…). The HH00/HH15/HH45 files
  (~650 KB) carry only `UTC` + `CIG`/`VIS`/`OBV` for 3 hours. `lavtxt_ext` (HH30, 2 MB) is hours 26–38
  — not used (our "48 h" view takes LAMP as far as the 25 h bulletin goes). CONTEXT.md's old name
  `lmp_lavtxt.tCCCCz` does not exist.
- **Timing seen:** at 14:50Z the NBM 13Z text and the LAMP 1330 bulletin were there; the MAV 12Z
  was still 404 (06Z was there). The worker records `available_at` for every run, which will give
  real latencies.

## Layout (all four)

```
 KDFW   NBM  NBH GUIDANCE    11/25/2026  1300 UTC                    header: id, product, cycle
 UTC  14 15 16 17 18 19 20 21 22 23 00 01 02 03 …                    valid hour (UTC)
 TMP  36 39 42 45 47 49 50 51 51 50 46 44 43 42 …
 CIG -88-88-88-88-88 …            VIS 100100100100 …                 cells can touch
```

- Label in columns 1–3, then **3-character cells from column 5**. Cells are read by position (rows
  like `-88-88` and `100100` have no spaces). A blank cell = element not given at that time.
- Header: `NBM  NBH`, `NBM  NBS`, `GFS MOS`, `GFS LAMP` + `GUIDANCE MM/DD/YYYY HHMM UTC`.
  The LAMP "cycle" is the issuance time (e.g. 13:30Z); it is the run key in `model_runs`.
- A block runs from its header to the next header.

## Valid times

| Product | Rule | Check |
|---|---|---|
| NBH | `UTC` row: each column is the next occurrence of that hour after the previous one, starting after the cycle (13Z run → 14Z … 14Z next day, 25 columns) | strictly increasing |
| NBS | `FHR` row: valid = cycle + FHR hours (05 … 71, every 3 h) | `UTC` row must equal the FHR time's hour |
| MAV | `HR` row (UTC hours) like NBH: 3-hourly, the last 3 columns 6-hourly (06Z run: 12Z … 06Z on day 3) | `DT` row: each `/NOV  26` falls in the column of that UTC date's first hour |
| LAV | `UTC` row like NBH: 25 hourly columns from the hour after the issuance | strictly increasing |

A DT/FHR disagreement rejects the block (the station is recorded as failed for that run; nothing
is guessed).

## Elements decoded

Only what the product prints and EdgeFront plots:

| Row | Variable | Unit | Products | Evidence |
|---|---|---|---|---|
| `TMP` | temp | °F | all | first-hour values vs the METARs at the same hour, all 28 stations: mean difference −0.1 to +0.1 °F (MAE 1.1–2.0) for LAV/NBH/NBS/MAV — clearly °F |
| `DPT` | dewpt | °F | all | same rows/scale as TMP |
| `WSP` | wind | kt | all | vs METAR (kt): LAV mean −0.07 kt (vs mph scale −1.29), NBH +0.18 (−1.04); MAE also lower as knots. MAV/NBS at 6 h lead do not separate kt from mph (light winds). MOS/NBM station bulletins are documented in knots; the MDL pages (vlab.noaa.gov) refused automated fetches (HTTP 403), so the documentation could not be quoted — see CONTEXT §14 Q24 |
| `SKY` | cloud | % (0–100) | NBH, NBS | values 0–100; KMIA 90–93 under an overcast METAR |
| `CLD` | cloud | category `CL FW SC BK OV` | MAV, LAV | the only codes seen (all 28 stations, 4 bulletins) |

Stored: °F → °C for temp/dewpt (the native °F value and unit are kept too), kt as is. **RH** is
not in any of these bulletins: it is computed from T/Td (Magnus, §6.5) and flagged `is_computed`.

Not decoded (present, not used in v1): TSD, DSD, WBG, SSD, WDR, WSD, GST, GSD, WGS, P01/P06/P12,
Q01/Q06/Q12, T01/T03/T06/T12, PZR/PSN/PPL/PRA/POZ/POS/TYP, S01/S06/SNW, SLV, I01/I06, CIG/CCG,
MVC/IFC/LIC/LCB, VIS/CVS/MVV/IFV/LIV, OBV, MHT, TWD/TWS, SOL, DUR, TXN/XND, X/N, PPO/PCO/PC1/LP1/
LC1/CP1/CC1.

## Missing values

No missing value appeared in TMP/DPT/WSP/SKY/CLD in the samples. `-88` appears only in CIG/LCB
(not decoded). The decoder accepts signed integers (winter temperatures below 0 °F); any other
cell is recorded as a decode error for that cell and skipped — never filled.

## Station coverage (2026-11-25)

All 28 registry stations are present in all four products (NBH/NBS 9,576 blocks; MAV ~2,318; LAV
2,313).
