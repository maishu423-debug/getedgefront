# EdgeFront — Project Context (living document)

> **Read this file first, every session.** It is the single source of truth for what we are building, why, and how.
> When a decision changes or a phase finishes, update the relevant section **and** add a line to §15 Progress log.
> If code and this file disagree, stop and ask the owner which one is right.

- **Product:** EdgeFront, a weather data platform for traders in U.S. weather markets (Kalshi, Polymarket, Robinhood)
- **Domain:** `getedgefront.com` (purchased)
- **Version being built:** v1 (free tier only; Premium is shown on the pricing page but not built)
- **Last updated:** 2026-11-24

---

## 1. Product in one paragraph

EdgeFront shows **observed weather at the exact U.S. stations that weather markets settle on**, next to the official NWS products and third-party model guidance for those stations, each value with its **source and time stamp**. We deliver data; we do **not** forecast, recommend trades, show market prices, or decide anything for the user. Free users get hourly METARs, ASOS Daily Summaries (DSM), the NWS forecast and model guidance. Premium (later) adds continuous 5-minute HFMETAR data, a live station map and more sources.

### Non-negotiable principles
1. **Never invent data.** No made-up readings, no filling gaps by interpolation, no "estimated" values presented as observed. A missing value is shown as missing.
2. **Every value carries its source and its time.** Observation time is separate from when we fetched it.
3. **Honest freshness.** Show how old the data is. A stale reading is labelled stale, never shown as "live".
4. **Label third-party content.** The NWS forecast is labelled FORECAST · NWS. Model output is labelled MODEL DATA with model, run (cycle) and producer. EdgeFront has no forecast of its own.
5. **No advice.** No "buy/sell", no rankings of models, no market prices or odds, no venue logos. Venue names are plain text identifying which markets use a station.
6. **U.S. stations only** in v1.

---

## 2. Tiers

| | Free (v1, built) | Premium (later, pricing page only in v1) |
|---|---|---|
| Hourly METAR + SPECI (raw + decoded) | ✅ | ✅ |
| NWS ASOS Daily Summary (DSM) | ✅ | ✅ |
| NWS forecast (today + hourly) | ✅ | ✅ |
| Model guidance chart (GFS, IFS, AIFS, NBM, GFS-MOS, LAMP, PFM) | ✅ | ✅ |
| Current temp / high so far / observed chart | From METAR | From 5-min HFMETAR |
| Continuous 5-minute HFMETAR | 🔒 | ✅ |
| Live station map | 🔒 | ✅ |
| More data sources | — | ✅ (later) |

v1 has **no accounts, no payments and no auth**. Premium elements appear as locked buttons that link to `/pricing`. The pricing page lists Premium features with a **"Coming soon"** state. It does not collect emails (open question Q5).

---

## 3. Architecture

```
                         ┌───────────────────────── Railway (Hobby) ─────────────────────────┐
 aviationweather.gov ──▶ │                                                                    │
 api.weather.gov    ──▶  │  worker (Python, APScheduler) ──▶ PostgreSQL ◀── api (FastAPI)     │
 NOMADS / AWS (NOAA) ──▶ │        ingest + parse + store                       ▲              │
 ECMWF open data    ──▶  │                                                     │ private net  │
                         │                                   web (Next.js) ────┘              │
                         └──────────────────────────────────────▲─────────────────────────────┘
 LDM server "ldm" (DigitalOcean)                                │ HTTPS (getedgefront.com)
   pqact → /home/ldm/data/madis/hfmetar/   (Premium, v2: not used in v1)       │
   madis-publisher → /home/ldm/data/madis/ready/                users
   madis-api (FastAPI, 127.0.0.1:8000, Bearer token)
```

- **web**: Next.js (App Router, TypeScript, Tailwind, ECharts). The only public service. Server components fetch from **api** over Railway private networking. Browser-side calls go through Next.js route handlers (`/api/*` proxy), so the FastAPI service is not exposed publicly.
- **api**: FastAPI, read-only JSON for the website. No upstream calls on request: it reads only from Postgres.
- **worker**: one Python process running every ingest job on a schedule (APScheduler). Upstream sources are contacted only by the worker.
- **PostgreSQL**: Railway Postgres (plain Postgres 16; TimescaleDB is not needed at this data volume). Watch the **5 GB volume cap** (§9 retention).
- **No Redis** in v1.
- **Shared Python package** `edgefront_core` (DB models, parsers, time/unit helpers) used by both api and worker.

### Tech choices
| Area | Choice |
|---|---|
| Frontend | Next.js (current stable, App Router), React, TypeScript (strict), Tailwind CSS, Apache ECharts, `next/font/google` (Space Grotesk, Inter, JetBrains Mono) |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, psycopg 3, httpx |
| Jobs | APScheduler (in the worker process), with jitter and per-job locks |
| Weather formats | `metar` (python-metar) or own parser for METAR (see §6.1); `herbie-data` + `cfgrib`/`eccodes` (GFS/NBM GRIB); `ecmwf-opendata` (IFS/AIFS) |
| Package mgmt | `uv` for Python, `pnpm` for Node |
| Tests | pytest (parsers use **real saved upstream files** as fixtures), Vitest (frontend utils), Playwright smoke test (home + station page) |
| Local dev | Docker Compose: postgres, api, worker, web |
| Deploy | Railway: services `web`, `api`, `worker`, `postgres`; Dockerfile per service |

### Repository layout (target)
```
edgefront/
  CONTEXT.md                  ← this file
  design/                     ← UI mockups (reference only, see §10)
    Home.dc.html
    Station.dc.html
  data/
    stations.yaml             ← station registry seed (§5)
  apps/web/                   ← Next.js
  services/api/               ← FastAPI app
  services/worker/            ← scheduler + jobs
  packages/core/              ← edgefront_core (models, parsers, utils)
    tests/fixtures/           ← real upstream samples + README of where each came from
  infra/
    docker-compose.yml
    railway.md                ← deploy notes
  .env.example
```

---

## 4. Data sources (v1)

**Rule:** every URL pattern below must be **verified against the live source before coding against it**. Save one real response per source to `packages/core/tests/fixtures/` with its URL and fetch time. If a pattern is wrong, fix it here.

All NWS/NOAA requests send `User-Agent: EdgeFront/1.0 (getedgefront.com; ${CONTACT_EMAIL})` (env var; owner to supply the email).

### 4.1 Hourly METAR + SPECI (free tier: core observations)
- **Source:** NOAA Aviation Weather Center Data API, `https://aviationweather.gov/api/data/metar` (no key). Rate limit is **100 requests/min per IP**; exceeding it returns 429 and can trigger a temporary block.
- **How:** one batched request per run for all registry stations, e.g. `?ids=KNYC,KLGA,...&format=json&hours=3`. Alternatively the bulk cache files listed at `https://aviationweather.gov/data/api/` (check that they exist). **Never** call per page view.
- **Schedule:** every 3 min (with jitter). Backfill on startup: `hours=36`.
- **Store:** raw text exactly as received, plus decoded fields (§6.1). Dedupe on (station, observed_at, report_type, raw_text hash). Keep corrections (`COR`) as new rows linked to the original.

### 4.2 NWS ASOS Daily Summary (DSM)
- **What:** NWS text product type `DSM`, issued by each station's ASOS several times a day. It gives max/min temperature **with times**, precipitation and peak wind for the climate day (midnight–midnight **local standard time**), and catches peaks between hourly METARs.
- **Source:** api.weather.gov products endpoints, e.g. `/products/types/DSM/locations/{LOC}` then `/products/{id}`. `{LOC}` is the 3-letter product location; it is often the station ID without "K" but **not always**, so it lives in the registry as `dsm_location`.
- **Schedule:** every 10 min.
- **Parsing:** the DSM is a coded text format. **Build the decoder only from real products** saved as fixtures (several stations, several issuances incl. the next-day final). Store the raw text always. If a field can't be decoded, store null and keep the raw text; don't guess.
- **Display:** "Today so far" (latest DSM for today's climate day) and "Yesterday, final".

### 4.3 NWS forecast
- **Source:** `https://api.weather.gov/points/{lat},{lon}` once per station (store office, gridX, gridY in the registry), then `/gridpoints/{office}/{x},{y}/forecast` and `/forecast/hourly`.
- **Schedule:** every 30 min per station; honour `Cache-Control`/`Expires`; retry with backoff on 5xx (the API has frequent transient errors).
- **Display:** today's high (daytime period) and tonight's low, short text for Today/Tonight, a 7-slot hourly strip (temp + precip chance), issued time and office. If today's daytime period has passed, show "—" for the high rather than tomorrow's.

### 4.4 Model guidance (launch set)
Store values at the station for each run: `temp`, `dewpt`, `wind_speed` (kt), `cloud` (% or category), and `rh` (computed from T/Td when not supplied, marked computed). **No interpolation in time or space**: plot only the times the product provides; for gridded models use the **nearest grid point** and store its lat/lon.

| Model (label) | Producer | Source (verify) | Format | Notes |
|---|---|---|---|---|
| **NBM** | NWS (National Blend) | NOMADS `blend` text bulletins: NBH (hourly, ~1–25 h) and NBS (3-hourly, to ~72 h) | Text | Station bulletins use the nearest usable grid point |
| **GFS-MOS** | NWS MDL | NOMADS `gfs_mos` MAV bulletins, cycles 00/06/12/18 | Text | 3-hourly; cloud is categorical (CL/FW/SC/BK/OV) |
| **LAMP** | NWS MDL | NOMADS `lmp` LAV text bulletins (`lmp_lavtxt.tCCCCz`), hourly 1–25 h | Text | The design calls this "GLMP"; v1 uses **station LAMP** and labels it **LAMP** |
| **PFM** | NWS forecast office | api.weather.gov products type `PFM` for the station's office; parse the block for the station's point | Text | Not every station has a PFM point: nullable |
| **GFS** | NOAA/NCEP | NOAA AWS open-data bucket or NOMADS, via Herbie (byte-range downloads of only the needed fields using `.idx`) | GRIB2 0.25° | Fields: TMP 2 m, DPT 2 m, UGRD/VGRD 10 m, TCDC; hourly to 54 h |
| **IFS** | ECMWF | ECMWF open data via `ecmwf-opendata` (or AWS mirror) | GRIB2 0.25° | Params `2t`, `2d`, `10u`, `10v`, `tcc`. Licence **CC BY 4.0, attribution required** |
| **AIFS** | ECMWF | ECMWF open data, `model="aifs-single"` | GRIB2 0.25° | Different file naming from IFS: use the package. CC BY 4.0 |

- **Later (not v1):** GEFS (and the "GEFS spread" toggle), HGEFS (source unknown: open question Q2).
- **Do not use Open-Meteo** (its free tier is non-commercial, and it would put a middleman between us and the original runs).
- **Schedule:** poll every 10–15 min for new cycles. Process each new run once: download, extract all registry stations in one pass, store, record `available_at` (when we first saw it) and `fetched_at`.
- **Retention:** keep the latest 4 runs per model (§9).

### 4.5 5-minute HFMETAR: Premium (v2). NOT built in v1
> Reference notes for the Premium version only. In v1, do not build any HFMETAR ingest, table, job, proxy or UI beyond the locked "5-minute data · Premium" links.
- **Upstream:** NOAA MADIS HFMETAR via Unidata LDM on the owner's server `ldm`.
- **On the LDM server:**
  - `pqact.conf`: `FSL2 ^FSL\.CompressedNetCDF\.MADIS\.(hfmetar\.[0-9]{8}_[0-9]{4}\.gz)$` → `FILE -overwrite -close /home/ldm/data/madis/hfmetar/\1`. Each hourly file is **rewritten repeatedly for about 2 h 40 min** after its hour starts.
  - `madis-publisher.service` copies validated snapshots into `/home/ldm/data/madis/ready/`. Its cadence is **unknown** (it looks like about once an hour: open question Q3). It must run every 2–5 min for real 5-minute data.
  - `madis-api.service` (owner-built FastAPI, `/opt/madis-api/app.py`) runs uvicorn on **127.0.0.1:8000**, Bearer token `MADIS_API_TOKEN`, and serves `ready/`:
    - `GET /health` (no auth) → `{status, service, latest_file, checked_at}`
    - `GET /api/v1/hfmetar/files` → `{files:[{name,size_bytes,modified_at}]}` newest first
    - `GET /api/v1/hfmetar/latest` → newest gzip file
    - `GET /api/v1/hfmetar/{hfmetar.YYYYMMDD_HHMM.gz}` → that gzip file (whole netCDF, all stations, ~1.2 MB)
- **To reach it from Railway:** reverse proxy (Caddy) on e.g. `ldm.getedgefront.com` with automatic HTTPS → `127.0.0.1:8000`. Never send the token over plain HTTP. Template goes in `infra/ldm/`.
- **Planned v2 worker job:** every 2 min, list files; download only files whose `modified_at` changed; gunzip; open with xarray/netCDF4; keep registry stations; upsert readings keyed by (station, observed_at); save only new or changed readings; retention 7 days.
- **Field names:** discover them from a real file (`ncdump -h`) and record the mapping here. **Do not guess.**
- Premium only; nothing of this exists in v1.

---

## 5. Station registry

- File: `data/stations.yaml`, loaded into the `stations` and `station_venues` tables by an idempotent seed command (`python -m edgefront_core.seed`).
- Each venue mapping carries `verified: false` until someone checks the venue's current market rules and fills `rules_url` and `verified_at`. **Unverified mappings still show**, and a site-wide note says venue labels are being verified.
- Venues settle on **different stations and sources**, often for the same city (e.g. NYC: Kalshi → KNYC Central Park; Polymarket/Robinhood → KLGA LaGuardia). Kalshi markets historically settle on the NWS Daily Climate Report (CLI); one recent source says Kalshi moved daily temperature settlement to The Weather Company data from Aug 14, 2026; Polymarket and Robinhood markets often name a Weather Underground station history. **Verify each.**
- Enrichment command (`python -m edgefront_core.enrich_stations`): fill `lat`, `lon`, `elevation_m`, `name` (from aviationweather station info or NWS `/stations/{id}`), `nws_office`, `grid_x`, `grid_y` (from `/points`), `tz` (IANA). `dsm_location` and `pfm_point` must be checked by hand.

### Seed list (illustrative; ALL venue mappings unverified)
| Station | Name | TZ | Venues (unverified) |
|---|---|---|---|
| KNYC | New York · Central Park | America/New_York | Kalshi |
| KLGA | New York · LaGuardia | America/New_York | Polymarket, Robinhood |
| KBOS | Boston · Logan | America/New_York | Kalshi, Robinhood |
| KPHL | Philadelphia Intl | America/New_York | Kalshi, Robinhood |
| KDCA | Washington · Reagan National | America/New_York | Kalshi, Robinhood |
| KATL | Atlanta · Hartsfield-Jackson | America/New_York | Kalshi, Polymarket, Robinhood |
| KCLT | Charlotte Douglas | America/New_York | Robinhood |
| KMIA | Miami Intl | America/New_York | Kalshi, Polymarket, Robinhood |
| KJAX | Jacksonville Intl | America/New_York | Robinhood |
| KDTW | Detroit Metro | America/Detroit | Kalshi |
| KMDW | Chicago · Midway | America/Chicago | Kalshi |
| KORD | Chicago · O'Hare | America/Chicago | Polymarket |
| KMSP | Minneapolis–St Paul | America/Chicago | Kalshi, Robinhood |
| KBNA | Nashville Intl | America/Chicago | Robinhood |
| KOKC | Oklahoma City · Will Rogers | America/Chicago | Robinhood |
| KDFW | Dallas/Fort Worth Intl | America/Chicago | Kalshi |
| KDAL | Dallas · Love Field | America/Chicago | Polymarket |
| KAUS | Austin-Bergstrom | America/Chicago | Kalshi, Polymarket, Robinhood |
| KSAT | San Antonio Intl | America/Chicago | Kalshi |
| KHOU | Houston · Hobby | America/Chicago | Kalshi, Polymarket |
| KSDF | Louisville · Muhammad Ali Intl | America/Kentucky/Louisville | Kalshi |
| KDEN | Denver Intl | America/Denver | Kalshi |
| KBKF | Denver · Buckley | America/Denver | Polymarket |
| KPHX | Phoenix · Sky Harbor | America/Phoenix | Kalshi, Robinhood |
| KLAX | Los Angeles Intl | America/Los_Angeles | Kalshi, Polymarket, Robinhood |
| KSFO | San Francisco Intl | America/Los_Angeles | Kalshi, Robinhood |
| KSEA | Seattle–Tacoma | America/Los_Angeles | Kalshi, Polymarket, Robinhood |
| KLAS | Las Vegas · Harry Reid | America/Los_Angeles | Kalshi |

YAML shape:
```yaml
- id: KNYC
  name: "New York · Central Park"
  city: "New York"
  state: NY
  tz: America/New_York
  dsm_location: NYC          # verify
  pfm_point: null            # verify
  venues:
    - venue: kalshi
      market: "Highest temperature in NYC"
      settlement_source: "NWS Daily Climate Report (CLI) via venue rules"  # verify
      rules_url: null
      verified: false
      verified_at: null
```

---

## 6. Definitions and calculations

### 6.1 METAR decoding
- Keep `raw_text` verbatim. Decode: type (METAR/SPECI), observation time, wind dir/speed/gust (kt), visibility (statute miles), sky layers (cover + base ft), temperature/dew point, altimeter (inHg), SLP (hPa), and these remarks groups:
  - `T` group: temperature/dew point in **tenths of °C**. Prefer it over the whole-°C main body value; record which one was used (`temp_precision = 'tenths' | 'whole'`).
  - `1snTTT` / `2snTTT`: 6-hour max/min (tenths °C), in the 00/06/12/18Z reports, covering the previous 6 hours.
  - `4snTxTxTxsnTnTnTn`: 24-hour max/min, in the midnight-LST report.
- Store temperatures in °C (numeric(4,1)). Convert to °F only for display, rounded half away from zero to whole °F. Show °F everywhere in v1 (U.S. traders); there is no unit toggle.
- Use python-metar only if fixture tests prove it handles every group above; otherwise write a focused parser. Either way, **parser tests use real METARs** saved from the API.

### 6.2 Local day
- Each station's **climate day = midnight to midnight local standard time (LST)**, which is how NWS DSM/CLI work. During daylight saving time that is 1:00 AM to 1:00 AM local clock time.
- Store `day_basis` per station (default `LST`). Some venues use the local calendar day (e.g. Weather Underground history). Label the basis on the station page.

### 6.3 "High so far" (free tier)
- `high_so_far` = the max of:
  1. the temperatures of all METAR/SPECI reports observed within today's climate day, and
  2. 6-hour max groups whose 6-hour window lies **entirely** inside today's climate day.
- Return its value, the time and the report it came from, plus `precision` (tenths/whole).
- UI copy: "From the HH:MMZ METAR (h:mm AM CST) · highest hourly METAR since local midnight. The DSM below includes peaks between reports."
- **New-high events** (homepage feed + "NEW" badge): when a stored report makes `high_so_far` increase, insert a `daily_high_events` row (from → to). Skip the first report of the day. The "NEW" badge means the event happened within the last 60 min.

### 6.4 Freshness
- `age = now − observed_at`. A station's METAR is **stale** if older than 90 min (configurable): show an amber "Stale · last report X min ago" state.
- A source is unhealthy if its last successful job is older than 3× its schedule. It is shown on the data status strip.

### 6.5 Derived values
- RH is computed from T/Td (Magnus: 17.625, 243.04 °C) and always labelled "computed".
- Wind is shown in kt; direction in degrees plus a compass point.
- Cloud categories map to midpoints for plotting only (CLR 0, FEW 19, SCT 44, BKN 75, OVC 100), with the category shown in tooltips.

---

## 7. Database schema (Alembic migrations)

All timestamps are `timestamptz` (UTC). Every observation and product row keeps `source`, `fetched_at` and `ingested_at`.

- `stations` (id PK `KNYC`, name, city, state, lat, lon, elevation_m, tz, day_basis, nws_office, grid_x, grid_y, dsm_location, pfm_point, active bool, created_at, updated_at)
- `station_venues` (station_id FK, venue enum[kalshi, polymarket, robinhood], market, settlement_source, rules_url, verified bool, verified_at) — PK (station_id, venue)
- `metar_reports` (id, station_id, report_type, observed_at, raw_text, raw_hash, is_correction, temp_c, dewpt_c, temp_precision, wind_dir_deg, wind_vrb bool, wind_kt, gust_kt, vis_mi, sky jsonb, altim_inhg, slp_hpa, max6h_c, min6h_c, max24h_c, min24h_c, source, fetched_at, ingested_at) — UNIQUE (station_id, observed_at, report_type, raw_hash); index (station_id, observed_at desc)
- `daily_high_events` (id, station_id, climate_date, from_c, to_c, report_id FK, observed_at)
- `dsm_products` (id, station_id, product_id UNIQUE, issued_at, climate_date, is_final, max_temp_f, max_time_local, min_temp_f, min_time_local, precip_in, peak_wind_kt, peak_wind_dir, peak_wind_time_local, raw_text, decode_errors jsonb, fetched_at)
- `nws_forecasts` (id, station_id, office, generated_at, update_time, periods jsonb, hourly jsonb, fetched_at) — keep latest 3 per station
- `model_runs` (model, cycle_time, available_at, fetched_at, status, source_url, notes) — PK (model, cycle_time)
- `model_values` (model, cycle_time, station_id, valid_time, variable, value, unit, is_computed, grid_lat, grid_lon) — PK (model, cycle_time, station_id, valid_time, variable)
- `hf_observations` (**v2, do not create in v1**) (station_id, observed_at, temp_c, dewpt_c, wind_dir_deg, wind_kt, gust_kt, altim_pa, vis_m, qc jsonb, file_name, file_modified_at, ingested_at) — PK (station_id, observed_at)
- `source_health` (source PK, last_success_at, last_attempt_at, last_error_at, last_error, last_item_time, notes)

---

## 8. Public API (FastAPI, read-only, `/api/v1`)

All responses include `generated_at` and, per block, `source` + times. Errors distinguish "no data yet" (200, `status: "no_data"`) from "upstream down" (`status: "stale"` with `last_success_at`).

| Endpoint | Returns |
|---|---|
| `GET /health` | service + DB ok |
| `GET /status` | per-source health (data status strip) |
| `GET /stations?venue=` | board rows: id, name, tz, venues[], latest METAR (temp, observed_at, age), high_so_far (value, time), nws_today_high, is_stale, fresh_high |
| `GET /stations/{id}` | station meta + venues + day basis + local time + "day ends in" |
| `GET /stations/{id}/current` | latest METAR summary + high_so_far |
| `GET /stations/{id}/metars?hours=24` | reports newest first, raw + decoded |
| `GET /stations/{id}/observed?hours=6\|24` | series from METARs: temp, dewpt, rh(computed), wind, gust, altim, sky blocks |
| `GET /stations/{id}/dsm` | today-so-far + yesterday-final (decoded + raw) |
| `GET /stations/{id}/forecast` | NWS today/tonight + hourly strip |
| `GET /stations/{id}/models?var=temp\|dewpt\|wind\|cloud\|rh&span=today\|48h` | per model: run, available_at, points [valid_time, value]; plus observed overlay from METARs |
| `GET /feed/new-highs?limit=10` | latest daily_high_events with station names |

Add OpenAPI docs in dev only. Use ETag/`Cache-Control: max-age=30` on read endpoints.

---

## 9. Retention (5 GB Railway volume)

| Table | Keep |
|---|---|
| metar_reports | 400 days |
| daily_high_events | 400 days |
| dsm_products | 400 days |
| nws_forecasts | latest 3 per station |
| model_runs / model_values | latest 4 runs per model |

A nightly worker job prunes and logs row counts and DB size. Alert in logs when DB size exceeds 3 GB.

---

## 10. UI specification

Mockups: `design/Home.dc.html` and `design/Station.dc.html`. They are written in a design-tool format (`<x-dc>` templates + a `DCLogic` class with **sample data generators**). Use them for **layout, copy, colours, spacing and states only**. Rebuild the UI in Next.js + Tailwind + ECharts; do not copy the runtime, and never ship the sample data.

### 10.1 Design tokens
- Colours: page `#F4F5F2`; surface `#FFFFFF`; border `#DDE1DC`; hairline `#ECEFEC`; ink `#101A1C`; text-2 `#2A3533`; muted `#4A5552` / `#56625F`; brand teal `#0A6E69` (hover `#064F4B`, tint `#E6F2F1`); temperature `#C24E12`, high emphasis `#B2450D`; dew point `#1F5FA8`; RH `#6B4FA0`; wind `#0A6E69`, gust `#7FB8B4`; pressure `#3D4A47`; fresh `#1A7F4B` (halo `#DDF1E5`); premium/lock bg `#FFF1E2` text `#8A4100`; forecast/model badge bg `#EDE8F6` text `#4B3488`; footer `#101A1C`.
- Sky cover: CLR `#EEF1EF`, FEW `#D5DEE6`, SCT `#A9BBCB`, BKN `#5F7488`, OVC `#33424F`; missing data `#F1ECE2`.
- Model colours: IFS `#1F5FA8`, GFS `#C24E12`, GEFS `#C77A16`, HGEFS `#7A4310`, AIFS `#B4235A`, GFS-MOS `#7D6A00`, NBM `#0A6E69`, LAMP `#3F8F3A`, PFM `#6B4FA0`; observed line `#101A1C` (3 px).
- Type: headings Space Grotesk 600–700; body Inter; all numbers, times, station codes and METAR text in JetBrains Mono.
- Radii: cards 14 px, big stat cards 16 px, buttons 8–9 px, pills 999 px. Max content width 1280 px, side padding 32 px.
- Accessibility: WCAG AA contrast; real `<button>`/`<a>`; `aria-pressed` on toggles; charts have text summaries; keyboard navigable; touch targets ≥ 40 px. Pages must work at phone width (tables scroll horizontally inside their box; header wraps).

### 10.2 Homepage `/`
1. Header: logo (front-line mark + "EdgeFront"), nav: Stations · Map (PRO lock pill → `/pricing`) · Pricing · Sign in (disabled/"coming soon" in v1).
2. Hero: H1 "Observed weather at the U.S. stations weather markets settle on." + subline + large search (city, station code, market name). Results go to the station page; no match → friendly empty state.
3. Data status strip (dark): status time, METARs fetched, DSM latest, NWS forecasts updated, models in (latest run per model), "5-min feed: Premium". Built from `/status`.
4. Station board (compact table): filter tabs All / Kalshi / Polymarket / Robinhood; sort tabs By time zone (default, East→West groups) / A–Z. Group header: zone name, local time, "Local day ends in Xh Ym" + progress bar. Columns: Station (code + name, link), Venues (plain grey tags), Now (°F), High so far (°F, time, NEW badge within 60 min), NWS fcst high, Last METAR (time + age; stale state), chevron link. Note under the table explaining that "high so far" ≠ settlement value.
5. Side column: "Recent new highs" feed (time, station, from → to °F) and a locked Premium map teaser (blurred illustration + "See Premium plans").
6. Footer: sources, independence note ("not affiliated with Kalshi, Polymarket or Robinhood"), terms/privacy links, "Data is provided as received. You decide how to use it."

### 10.3 Station page `/station/[id]`
1. Header as homepage.
2. Station title: code (46 px), full name, mono meta line (lat/lon, elevation, ASOS, local time zone).
3. Two large cards: **Current temperature** (latest METAR, time Z + local, age, green dot, or amber when stale) and **Today's high so far** (§6.3 copy). Beside them, the **NWS forecast · Today** card (FORECAST badge, office + issued time, high/low tiles, Today/Tonight text, 7-slot hourly strip, "EdgeFront does not make forecasts" + link to weather.gov).
4. **ASOS Daily Summary (DSM)**: two panels, "Today so far" (issued time) and "Yesterday, final": Max temp + time, Min temp + time, Precip, Peak gust. "View product text" expands the raw DSM. Note that DSM can differ from the METAR high.
5. **Observed conditions** chart (ECharts, shared time axis, stacked panels): toggles Temp & dew point · Humidity (computed) · Wind (sustained line + gust range bars) · Sky (METAR cover strip) · Pressure (off by default). Range 6 h / 24 h. Points at each METAR/SPECI time; **gaps where reports are missing** (no line across gaps > 90 min). Readout row for the latest METAR. Locked "5-minute data · Premium" button → `/pricing`. Tooltip shows exact values, report time and type.
6. **Hourly METAR reports**: Raw / Decoded toggle; newest first; SPECI highlighted; last 12 h with "Show all 24 hours".
7. **Model guidance**: MODEL DATA badge; variable tabs Temp / Dew pt / Wind / Cloud / RH; Today / 48 h; "Latest run per model" select (v1: latest only); model chips grouped Global (IFS, GFS) · AI (AIFS) · Statistical (GFS-MOS, NBM, LAMP) · NWS (PFM) with All/None; chart with each model's line (markers at real valid times only) + observed METAR line on top + "Now" marker. Tooltip: model, run (cycle) and received time. Footnote: reference only; EdgeFront doesn't rank or blend models. Hide GEFS spread until GEFS exists.
8. Footer as homepage, plus ECMWF CC BY 4.0 attribution.

### 10.4 Other pages
- `/pricing`: Free vs Premium comparison (§2), Premium "Coming soon" button, FAQ (what "5-minute" means, data sources, no advice).
- `/sources`: each source with producer, what we use, update cadence, licence/attribution, time-stamp definitions (observed / fetched / age), how "high so far" and the climate day work.
- `/terms`, `/privacy`: placeholder pages clearly marked "Draft — pending legal review". **Do not write legal terms.**
- 404 and per-section error/empty/stale states.

---

## 11. Phases (v1)

Each phase ends with: tests passing, a short demo note, CONTEXT.md updated, and a **stop for owner review**.

| Phase | Scope | Done when |
|---|---|---|
| **0. Foundation** | Monorepo, tooling (uv, pnpm, ruff, mypy, eslint, prettier), Docker Compose (postgres/api/worker/web), `.env.example`, CI (lint + tests), `design/` + CONTEXT.md in repo | `docker compose up` gives a hello page, `/api/v1/health` ok and a worker heartbeat; CI is green |
| **1. Data model + registry** | Alembic schema (§7), `stations.yaml` seed, enrichment command, `source_health` | Seed + enrich run idempotently; 28 stations with lat/lon/tz/office/grid; unverified venues flagged |
| **2. METAR pipeline** | Fetch job, parser (§6.1) with real fixtures, dedupe/corrections, high-so-far + new-high events (§6.2–6.3), API: stations, current, metars, observed, feed, status | 24 h of real METARs for all stations; parser tests cover T-group, 6 h/24 h groups, SPECI, COR, VRB, missing fields; high-so-far correct across a DST and an LST-midnight test case |
| **3. DSM + NWS forecast** | DSM fetch + decoder (real fixtures, raw kept), NWS points/forecast/hourly with backoff + caching, API: dsm, forecast | Today/yesterday DSM decoded for most stations; undecodable ones show raw text; forecasts refresh; 5xx handled |
| **4. Frontend v1 (no models)** | Next.js pages: home, station (all sections except models), pricing, sources, terms/privacy placeholders; tokens; ECharts observed chart; states; SEO metadata; responsive | Pages match the design; real data end-to-end; no sample data; Lighthouse accessibility ≥ 95; Playwright smoke passes |
| **5. Models** | Text bulletins first (NBM, GFS-MOS, LAMP, PFM), then GRIB (GFS via Herbie, IFS + AIFS via ecmwf-opendata); model_runs bookkeeping; models API; model chart UI; retention | Each model shows its latest run for all stations (or a clear "not available for this station"); runs/received times correct; memory use fits Railway |
| **6. Deploy + launch** | Railway services, private networking, env vars, custom domain + HTTPS, retention job, structured logs, uptime check, launch checklist | Site live on getedgefront.com; all sources healthy for 48 h; DB size and memory within limits |

---

## 12. Engineering conventions
- Python: ruff + mypy (strict-ish), typed Pydantic models for every API response; no business logic in route handlers.
- TypeScript strict; API types generated from FastAPI's OpenAPI (e.g. `openapi-typescript`) or hand-kept in one `types.ts`.
- Every ingest job: idempotent, retry with exponential backoff + jitter, timeout, updates `source_health`, logs `source`, `count_new`, `count_dup`, `latest_item_time`, `duration_ms`.
- Never fetch upstream from a web request path.
- Secrets only in env vars; `.env` is never committed.
- Times: store UTC; convert to station tz only for display; display both Z and local where the design does.
- Commits: small and descriptive; one branch per phase (`phase-2-metar`), merged after owner review.

## 13. Environment variables (`.env.example`)
```
DATABASE_URL=postgresql+psycopg://edgefront:edgefront@postgres:5432/edgefront
API_INTERNAL_URL=http://api:8000          # web → api (Railway: http://api.railway.internal:PORT)
CONTACT_EMAIL=                            # used in NWS User-Agent (owner to supply)
METAR_POLL_SECONDS=180
DSM_POLL_SECONDS=600
FORECAST_POLL_SECONDS=1800
MODEL_POLL_SECONDS=900
STALE_METAR_MINUTES=90
NEXT_PUBLIC_SITE_URL=https://getedgefront.com
```

## 14. Open questions (owner)
| # | Question | Default until answered |
|---|---|---|
| Q1 | Contact email for the NWS User-Agent | Placeholder env var; must be set before deploy |
| Q2 | Source of HGEFS | Not in v1 |
| Q3 | `madis-publisher` cadence (run `systemctl cat madis-publisher.service`) | Needed for Premium (v2) |
| Q5 | Pricing page: collect emails for a waitlist? | No; "Coming soon" only |
| Q6 | Verified station-to-venue list | Seed list, flagged unverified |
| Q7 | Day basis per venue (LST vs local calendar) | LST for all |
| Q8 | Premium price points | "Coming soon", no prices |

## 15. Progress log
- 2026-11-24 — Plan written. Designs: homepage + free-tier station page. Phase 0 not started.
- 2026-11-24 — Owner decision: 5-minute HFMETAR is Premium only and is **not built in v1** (no ingest, no table, no LDM proxy). v1 phases renumbered 0–6.
