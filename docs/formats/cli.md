# CLI — NWS Daily Climate Report: format note

Decoder: `packages/core/src/edgefront_core/parsers/cli.py`. Fixtures: `packages/core/tests/fixtures/nws_cli/` (23 products, 13 stations, fetched 2026-11-24 from api.weather.gov; URLs and times in the folder README). The decoder was also run on 156 recent CLIs from all 26 stations that publish one: 0 decode errors.

Everything below is what the samples show. Fields not listed are kept only in `raw_text`.

## Header

```
000
CDUS41 KOKX 240619          ← WMO heading, issuing office, DDHHMM (UTC)
CLINYC                      ← PIL: CLI + 3-letter location
...
CLIMATE REPORT
NATIONAL WEATHER SERVICE NEW YORK, NY
119 AM EST TUE NOV 24 2026  ← local issue time (we use the API's issuanceTime instead)
...THE CENTRAL PARK NY CLIMATE SUMMARY FOR NOVEMBER 23 2026...
VALID TODAY AS OF 0400 PM LOCAL TIME.   ← only on intraday issuances
```

| Field | Evidence | Decoded as |
|---|---|---|
| issuer | 4-letter office after the WMO heading (`KOKX`, `KFWD`, …) | `issuer` |
| correction | `CDUS44 KOUN 241431 CCA` + title `CLIMATE REPORT...CORRECTED...` (CLIOKC_202611241431); body adds a line `CORRECTED WIND DATA` | `is_correction = true`, `bbb = "CCA"` |
| climate date | `CLIMATE SUMMARY FOR <MONTH> <D> <YYYY>` — always present | `climate_date` |
| intraday vs final | intraday issuances carry `VALID TODAY AS OF hhmm AM/PM LOCAL TIME.` or `VALID AS OF hhmm AM/PM LOCAL TIME.` and their tables are labelled ` TODAY`; the next-morning final has no VALID line and is labelled ` YESTERDAY` | `kind = preliminary` (+ `valid_as_of_local`) or `final` |

Observed intraday times: 06:00/07:00 AM (DEN, AUS, SAT), 03:00–08:00 PM (most offices), 07:25 PM (SDF). Some offices issue several per day (BNA 3 PM + 6 PM; DFW 4 PM + 6 PM). Finals arrive ~00:30–02:30 local standard time.

A final can be re-issued unchanged (CLILAX 08:41Z and 09:06Z, both without BBB). The latest issuance for a day wins; both are kept.

## Temperature

```
TEMPERATURE (F)
 YESTERDAY
  MAXIMUM         69    139 PM  72    1931  51     18       49
  MINIMUM         50   1159 PM  14    1880  40     10       36
```

Columns (header `WEATHER ITEM OBSERVED VALUE TIME (LST) RECORD VALUE YEAR NORMAL VALUE DEPARTURE FROM NORMAL LAST YEAR`):

| Column | Evidence | Decoded |
|---|---|---|
| observed value (°F) | integer, `MM` = missing; may end in `R` (legend: "R INDICATES RECORD WAS SET OR TIED") | `max_temp_f` / `min_temp_f` |
| time (LST) | three spellings seen: `139 PM`, `1159 PM`, `2:53 PM` | `HH:MM` 24 h, local **standard** time (header says "(LST)") |
| record value + year | e.g. `72    1931` | not stored |
| normal | e.g. `51` | `normal_high_f` / `normal_low_f` — only when record + year were also matched, so columns are known to be aligned |
| departure | e.g. `18`, `-17` | `departure_high_f` / `departure_low_f` (same rule) |
| last year | sometimes absent (intraday issues) | not stored |

## Precipitation

```
PRECIPITATION (IN)
  YESTERDAY        0.00          1.84 1923   0.12  -0.12     0.00
```

The first `YESTERDAY`/`TODAY` line under `PRECIPITATION (IN)` is the day's total. Values seen: `0.00`, `0.01`, `T` (legend: trace), `MM` (missing). `T` → `precip_trace = true`, `precip_in = null`. Later `YESTERDAY` lines belong to SNOWFALL / DEGREE DAYS tables and are not read.

## Not decoded (on purpose)

Snowfall, degree days, wind, sky cover, humidity, the "normals for today" block (it refers to the *next* day), sunrise/sunset. Records are optional and not stored in v1.
