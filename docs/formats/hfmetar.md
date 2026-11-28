# HFMETAR (MADIS "1-minute ASOS") — format note (v2 Phase 9 B2)

Built from **real files**, not documentation: 26 hourly files fetched 2026-11-27 through the
owner's LDM API (24 consecutive complete hours, 2026-11-25 17Z → 2026-11-26 16Z, plus the
2026-11-27 15Z hour and two versions of the 17Z hour). Fixtures: `packages/core/tests/fixtures/hfmetar/`.

MADIS docs: [1-minute ASOS](https://madis.ncep.noaa.gov/madis_OMO.shtml) ·
[variables](https://madis.ncep.noaa.gov/sfc_OMO_variable_list.shtml) ·
[surface QC](https://madis.ncep.noaa.gov/madis_sfc_qc_notes.shtml) ·
[QC overview](https://madis.ncep.noaa.gov/madis_qc.shtml) ·
[surface notes](https://madis.ncep.noaa.gov/sfc_notes.shtml). MADIS calls this feed
"1-minute ASOS" (formerly HF-METAR): FAA ASOS/AWOS stations; "should not be considered to be
METAR observations" and has "no metar quality control" (`madis_metar.shtml`).

## File

- Name `hfmetar.YYYYMMDD_HH00.gz`: gzip of a **netCDF-3 classic** file (`CDF\x01`), ~1.2 MB
  compressed, ~19 MB uncompressed, ~12,000 records (1,021 stations) per hour.
- One file per UTC hour (`startTime`..`endTime` = HH:00:00–HH:59:59). LDM rewrites the current files
  about every 2 minutes for ~2 h 40 min; the publisher copies them when they change.
- Global attributes (excerpt): `title = "MADIS - Meteorological Surface - High frequency METAR"`,
  `Conventions = "MADIS surface observations, v1.0"`, `stationIdVariable = "stationId"`,
  `timeVariables = "observationTime,reportTime,receivedTime"`, `license = "To access MADIS data fill
  out the application at https://madis.ncep.noaa.gov/data_application.shtml. Some of the MADIS data are
  restricted. See …/madis_restrictions.shtml"`.
- Dimensions: `recNum` (unlimited, one record per station observation), `maxStaIdLen = 6`,
  `QCcheckNum = 10`, plus string lengths.
- Every record has `dataProvider = stationType = "HF-METAR"` (one provider: nothing restricted
  to exclude).

## Field map (what EdgeFront stores)

| MADIS variable | Units in file | Real grid (verified) | `hf_observations` column |
|---|---|---|---|
| `stationId` (char[6]) | — | ICAO, e.g. `KDFW` | `station_id` (registry stations only) |
| `observationTime` (double) | s since 1970-01-01 UTC | **every 5 min, :00…:55** | `observed_at` |
| `receivedTime` (double) | s since 1970 | ~2.4 min after obs | (latency) |
| `temperature` (float32) | kelvin | **whole °C** (8,048/8,048) | `temp_c`, `temp_precision = whole_c` |
| `dewpoint` (float32) | kelvin | **whole °C** (8,048/8,048) | `dewpt_c` |
| `windDir` (float32) | degree | multiples of 10° (2,471/2,471) | `wind_dir_deg` |
| `windSpeed` (float32) | m/s | **whole knots** (2,471/2,471) | `wind_kt` |
| `windGust` (float32) | m/s | whole knots (304/304) | `gust_kt` |
| `altimeter` (float32) | pascal | **0.01 inHg** (2,450/2,450) | `altim_inhg` |
| `visibility` (float32) | meter | statute miles, 1/16 steps (10, 9, 4 …) | `vis_mi` |
| `precipAccum` (float32) | mm | 0.01 in (0.254 mm steps) | `precip_in` |
| `<var>DD`, `<var>QCA`, `<var>QCR` | char, int | see QC | `qc` (jsonb, as provided) |
| `rawMessage` (char) | — | the record **as transmitted to MADIS**: a comma-separated LDAD mesonet record (e.g. `KDFW,1,26/11/27 17:00:00,0,0,1,12500,-999,-999,CLR, , ,10, ,0,16,-1,180,11,…,30.11,…`), **not a METAR**; present on every record of our stations | `raw_message` (v2 Phase 10b; shown as-is in the "Raw" view) |
| `skyCvr` (char, up to 3 layers) + `skyCovLayerBase` (float, m) | metres of a value reported in hundreds of feet | cover CLR/FEW/SCT/BKN/OVC; bases snap to whole 100 ft (CLR carries the 12,500 ft sensor limit, stored without a base); 255 of 298 records have a layer | `sky` jsonb `[{"cover","base_ft"}]` |
| `presWx` (char) | — | present weather as reported (rare: 2 of 298 records, `-RA`) | `pres_wx` |

Other variables in the file (not stored): `stationName`, `latitude`/`longitude`/`elevation`, `metarType` (always 1 for our stations), `autoRemark`, `operatorRemark`, `runwayVisualRange`, `densityAltitude`, status words per sensor. Raw, sky and weather (v2 Phase 10b) are kept current on rewrites like the QC fields, without counting as a value revision.

Missing values: `_FillValue = 3.4028235e+38` or `missing_value = -9999` → stored as null, never
filled. Floats are snapped to their grid (e.g. 288.1499938964844 K = 15 °C exactly in float32);
a value more than 0.01 off its grid is stored as is and flagged, never guessed.

## Temperature precision (Q35)

**Whole °C.** All 8,048 temperatures and 8,048 dew points of our stations in 26 hours are exact whole
°C. So a 5-minute value is only good to ±0.5 °C (±0.9 °F); the hourly METAR T-group (tenths °C,
itself a conversion of the station's whole-°F reading) is more precise. EdgeFront shows whole-°C
values with the possible station readings (`f_possible`, e.g. 17 °C → 62–63 °F).

**How the whole °C is produced** (owner B9 item 4): pairing 5-minute readings with METAR/SPECI
T-groups at the same station and minute gives **21 exact pairs** (METARs rarely fall on a 5-minute
mark; these are SPECIs at :10–:35). In all 21 the 5-minute °C equals the nearest whole °C of the
station's whole-°F reading (= NWS half-up of the T-group tenths), **0 mismatches**; 3 of them rule
out truncation. Small sample: the worker keeps pairing new readings and reports mismatches on
`/status` (`hfmetar.rounding_check`).

## Coverage (26 consecutive hours, 312 expected per station)

All our stations report every 5 minutes except: **KNYC and KBKF are not in the feed at all** (KNYC
Central Park is not an FAA ASOS; nearest in the feed: KLGA, KJRB, KTEB. KBKF is military; KDEN and
KAPA are nearby). Gaps: KBOS 297/312, KMSP 291/312, KSEA 288/312; all others 312/312.

## Rewrites (two versions of the same file, 5 minutes apart)

Version 2 of `hfmetar.20261127_1700.gz` (all 1,021 stations): **204 new records** (the :50/:55
observations), **0 removed**, 421 existing records changed, and in every one of them **only QC
fields** changed (letters and result words; e.g. temperature `V`→`Q` as later readings arrive for
the temporal check). **No measured value ever changed.** So: upsert by (station, observation time);
values are written once, QC fields are kept current; a value change would bump `revision`.

## QC (as documented by MADIS)

- `<var>DD`, data descriptor ([surface QC](https://madis.ncep.noaa.gov/madis_sfc_qc_notes.shtml)):
  `Z` preliminary, no QC · `C` coarse pass (level 1) · `S` screened (levels 1–2) · `V` verified
  (levels 1–3) · `X` rejected/erroneous (failed level 1) · `Q` questioned (passed 1, failed 2 or 3) ·
  `G` subjective good · `B` subjective bad. Levels: 1 validity; 2 internal, temporal and statistical
  spatial consistency; 3 spatial ("buddy") consistency. The file also lists `K`/`k` for temperature
  (not described on the MADIS pages; not seen in our data).
- `<var>QCA` (applied) / `<var>QCR` (results) bit words: 1 master, 2 validity, 4 reserved, 8 internal
  consistency, 16 temporal consistency, 32 statistical spatial, 64 spatial ("buddy"); 128–512 reserved.
  A results bit means that check was applied and **failed**.
- `<var>QCD`: departures from the QC estimates (not stored).
- Seen for our stations (26 h): temperature `V` 8,020 · `Q` 28 · `Z` 4.
- EdgeFront: **QC-failed = `X`, `Q` or `B`**. Stored with their flags, excluded from the 5-minute
  high/low (counted as `excluded_qc_count`), shown with a marker (Phase 10), never dropped silently.

## Latency

`receivedTime − observationTime` for our stations: P50 142 s, P95 146 s. **But a reading only
reaches the hourly file much later:** in a live run on 2026-11-28 (13 polls, 43 live readings),
observation → LDM file written was P50 715 s / P95 1,015 s, observation → stored P50 800 s /
P95 1,048 s. Example (2026-11-27): the 19:25Z readings (received 19:27Z) were not in the 19:32:42
file version and first appeared in the 19:37:58 one. The delay is in MADIS's file production and
LDM delivery, upstream of EdgeFront; the publisher adds ~30 s and our poll up to 60 s. So a
station's 5-minute data counts as stale after 30 min (`HF_STATION_STALE_MINUTES`), while the
worker alert for "no new readings at all" stays at 15 min. Measured continuously on `/status`.
