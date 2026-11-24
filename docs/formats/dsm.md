# DSM — ASOS Daily Summary: format note

Decoder: `packages/core/src/edgefront_core/parsers/dsm.py`. Fixtures (fetched 2026-11-24, URLs + times in each README):

- `packages/core/tests/fixtures/iem_dsm/` — 40 products, 15 stations, from the Iowa Environmental Mesonet AFOS archive (`/api/1/nwstext/{product_id}`). These are the CDUS27 products issued by the ARTCCs (KZNY, KZFW, …).
- `packages/core/tests/fixtures/nws_dsm/` — 12 products for KNYC/KMSP/KSAT from api.weather.gov (CXUS4x from the WFO).

The decoder was run on 97 real DSMs (85 IEM + 12 NWS): 0 decode errors. Meanings below were **confirmed by comparison with the same day's final CLI** (whose columns and units are labelled): max/min value and time and precipitation on 22 final DSMs, wind on 20 — all agreed.

## Layout

```
KLGA DS 0700 24/11 510048/ 440659// 70/ 44//0070016/00/00/00/00/00/
00/00/00/-/-/-/-/-/-/-/-/-/-/-/-/-/-/-/-/-/-/31210418/30270421=          ← intraday ("so far")

KLGA DS 23/11 701335/ 522359// 70/ 58//9780347/00/00/00/00/00/00/00/
00/00/…/00/95/33231645/ 33311644=                                       ← next-day final
```

Lines wrap anywhere after a `/`; the decoder joins them and removes the space after `/`. The product ends at `=`. Products from api.weather.gov also have `000`, the WMO line and the PIL above the body; the decoder starts at `KXXX DS`.

| Group | Example | Meaning | Evidence |
|---|---|---|---|
| station | `KLGA` | ICAO | always matches the PIL |
| `COR` | `KNYC DS COR 19/11 …` | correction | seen once (api.weather.gov, NYC) |
| `DS HHMM` | `DS 0700`, `DS 1500`, `DS 1800` | issue time, local **standard** time; marks an intraday ("so far") summary | LGA `DS 0700` entered 12:16Z = 07:16 EST; DFW `DS 1800` entered 00:06Z = 18:06 CST. Absent on the final issued after midnight → `final` |
| `DD/MM` | `23/11` | climate day (no year; taken from the issue date) | equals the CLI's "SUMMARY FOR" date |
| max group | `701335` | max °F `70` at `13:35` LST (TT[T]hhmm) | = CLI max + time on all 22 finals |
| min group | `522359` | min °F `52` at `23:59` LST | = CLI min + time on all 22 finals |
| first group after the second `//` (7 digits) | `9780347` | **not decoded** | meaning not provable from the samples |
| next group | `00`, `78`, `T` | **total precipitation, hundredths of an inch**; `T` = trace | BOS 78 = CLI 0.78; BOS 62 = 0.62; OKC 12 = 0.12; ATL 06 = 0.06; PHL/SEA/AUS `T` = CLI trace. On intraday issues it is the total so far |
| 24 groups | `00/…/-/-` | hourly precipitation; `-` = hour not reached yet | **not decoded** (not needed; totals above) |
| number before the wind groups (finals only) | `95`, `127` | **not decoded** | meaning not provable |
| `DDSSHHMM` (1st) | `33231645` | highest wind: from 330°, 23 **mph**, at 16:45 LST | = CLI "HIGHEST WIND SPEED/DIRECTION" (MPH) on 20/20 finals |
| `DDSSHHMM` (2nd) | `33311644` | highest gust: from 330°, 31 **mph**, at 16:44 LST | = CLI "HIGHEST GUST SPEED/DIRECTION" (MPH) on 20/20 finals |
| trailing | `/1`, `/2`, `/N/NN/N/N/NN/EW` | **not decoded** | meaning not provable |
| second temp pair | `70/ 44` | **not decoded** (it differs from the day's max/min, e.g. LGA 22/11 `59/ 53` vs max 63) | — |

## Issuance patterns seen

- Intraday issues at the station's own hours: 0200 (MIA), 0600/0700 (DEN, HOU, LGA, AUS), 0800 (PHL, PHX, SEA), 1400–1900 local (most). Several per day are normal (DFW 1500/1600/1800; ORD 1500/1600/1700).
- The final for day D is issued after local-standard midnight (≈ 05:00–08:30Z for U.S. zones), without `HHMM`.
- The same final can be transmitted twice (PHL 05:16Z and 05:46Z, identical text) → stored once (dedupe on station, climate date, issue key, raw hash).
- A station may have no "today so far" DSM in the morning: an empty state, not an error.

## Not handled because not seen

Negative temperatures (the samples have none) and three-digit precipitation totals (≥ 1.00 in). Such groups are recorded in `decode_errors` rather than guessed if they don't match the patterns above.
