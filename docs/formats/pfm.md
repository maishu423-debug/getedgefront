# PFM — NWS Point Forecast Matrices: format note

Decoder: `packages/core/src/edgefront_core/parsers/pfm.py` (point list: `parsers/stations.py`
`parse_pfm_points`). Fixtures: `packages/core/tests/fixtures/nws_pfm/` — 27 products from the
21 offices that hold our 26 PFM points, 2 issuances for FWD, OKX, VEF, EWX, LOX, MTR (fetched
2026-11-25; URL + UTC fetch time in the README); plus the two Phase 1 products in `nws_products/`.
Capture: `uv run python tools/capture_pfm.py [--cycles N] [--offices …]`.

Source: `https://api.weather.gov/products/types/PFM/locations/{office}` (newest first) →
`/products/{id}` → `productText`.

All 35 station blocks in the fixtures (all 26 registry points) decode with 0 errors.

## Point block

```
NYZ072-242100-                                    UGC line
Central Park-New York NY                          point name = registry `pfm_point`
40.78N  73.97W Elev. 16 ft                        lat/lon line
121 AM EST Tue Nov 24 2026                        issue time (local; zone abbreviation)

Date             Tue 11/24/26            Wed 11/25/26            Thu 11/26/26
EST 3hrly     04 07 10 13 16 19 22 01 04 07 10 13 16 19 22 01 04 07 10 13 16 19
UTC 3hrly     09 12 15 18 21 00 03 06 09 12 15 18 21 00 03 06 09 12 15 18 21 00

Max/Min                      49          36          48          44          57
Temp          45 43 46 48 47 44 40 39 37 36 42 47 46 45 45 45 45 45 48 50 52 53
Dewpt         29 27 23 18 18 20 20 21 21 21 21 21 25 29 30 33 35 37 38 41 42 47
RH            53 53 40 30 31 38 44 48 52 54 43 35 43 53 55 62 68 73 68 71 69 80
Wind dir      NW NW  N  N  N  N  N  N  N  N NE NE NE NE NE NE NE NE NE  E  E  E
Wind spd       8  9 10  8  5  4  4  4  5  5  5  5  5  5  6  8 10 12 14 19 23 21
Clouds        CL CL CL CL CL CL CL FW FW FW FW SC SC B1 B2 OV OV OV OV OV OV OV
…
(blank line, then a 6-hourly section: Date / EST 6hrly / UTC 6hrly / Min/Max / Temp / Dewpt /
 PWind dir / Wind char / Avg clouds / PoP 12hr …)
$$
```

**Lat/lon line formats seen** (35 blocks): `40.78N  73.97W Elev. 16 ft` (25),
`32.91N 97.03W Elev. 562 ft` (8, single space), `36.07N 115.16W Elev. (Average Over 2.5KM Grid Box): 2181 ft`
(2, VEF). All three parse.

**Zones seen** in the hour-row labels: EST, CST, MST (Denver and Phoenix), PST. The decoder also
knows the DST forms (EDT/CDT/MDT/PDT) for the summer; the UTC row check below catches a wrong one.

## Valid times

- The **3-hourly matrix does not start at the issue time**: VEF issued 10:32 PM PST starts at 1 PM
  the same day (cells blank until 09Z); OKX issued 1:21 AM starts at 4 AM.
- Rule: the first date label in the `Date` row gives the local date of the first column that ends
  to the right of where the label starts (the samples put it over column 1 or 2); the date steps
  forward each time the local hour wraps. UTC = local − zone offset.
- **Checks:** the computed UTC hour must equal the `UTC 3hrly` row in every column, and the first
  column must be within 24 h of the issue time; otherwise the block is rejected.

## Elements decoded (3-hourly section only)

| Row | Variable | Unit | Notes |
|---|---|---|---|
| `Temp` | temp | °F | |
| `Dewpt` | dewpt | °F | |
| `RH` | rh | % | the **product's own RH** (not computed) |
| `Wind spd` | wind | **mph** (stored native, converted to kt for display) | the public NWS forecast unit; owner spec Phase 5 |
| `Clouds` | cloud | category `CL FW SC B1 B2 OV` | `B1`/`B2` split "broken"; both plot at the BKN midpoint (§6.5) with the code shown — Q25 |

Cells are read **by column position**: each value is right-aligned with its UTC hour token.
Blank cells (before the forecast starts, or no value) are skipped.

Not decoded: Max/Min, Wind dir, Wind gust, PoP/QPF/Snow 12hr, Rain/Rain shwrs/Snow/Snowshwrs/Tstms/
Obvis, Wind chill/Min chill, hazard rows (High Wind, Wind, Freeze, Coast Flood, High Surf) and the
whole 6-hourly section (its "Avg clouds" is a period average, and the 3-hourly section already
reaches ~60 h).

## Coverage

26/28 stations have a point (CONTEXT §4.4). KMIA (nearest point 4.9 km) and KHOU (no Hobby point
in PFMHGX) → "Not available for this station".
