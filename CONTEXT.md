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
| Frontend | Next.js 16.4 (App Router, `cacheComponents: true`, Turbopack, `output: "standalone"`), React 19, TypeScript (strict), Tailwind CSS v4 (tokens in `globals.css` `@theme`), Apache ECharts, `next/font/google` (Space Grotesk, Inter, JetBrains Mono). Live data is read at request time with `await connection()` inside `<Suspense>`, so `next build` never calls the API; ~60 s freshness is done with `"use cache"` + `cacheLife` behind `await connection()` (Phase 4, §10.5), not the old `revalidate` export. ECharts is lazy-loaded on the client only (modular core). Bundled docs: `apps/web/node_modules/next/dist/docs/` |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, psycopg 3, httpx |
| Jobs | APScheduler (in the worker process), with jitter and per-job locks |
| Weather formats | `metar` (python-metar) or own parser for METAR (see §6.1); `herbie-data` + `cfgrib`/`eccodes` (GFS/NBM GRIB); `ecmwf-opendata` (IFS/AIFS) |
| Package mgmt | `uv` for Python, `pnpm` for Node |
| Tests | pytest (parsers use **real saved upstream files** as fixtures), Vitest (frontend utils), Playwright smoke test (home + station page) |
| Local dev | Docker Compose: postgres, api, worker, web |
| Deploy | Railway: services `web`, `api`, `worker`, `postgres`; Dockerfile per service |

### Repository layout (as built in Phase 0)
```
GetEdgeFront/                 ← repo root
  pyproject.toml, uv.lock     ← uv workspace (core, api, worker); ruff/mypy/pytest config
  conftest.py                 ← shared DB fixtures (TEST_DATABASE_URL = Postgres, else temp SQLite)
  package.json, pnpm-workspace.yaml, pnpm-lock.yaml, .nvmrc (Node 24 LTS)
  .github/workflows/ci.yml    ← python + web + docker jobs
  CONTEXT.md                  ← this file
  design/                     ← UI mockups (reference only, see §10)
    Home.dc.html
    Station.dc.html
  data/
    stations.yaml             ← station registry seed (§5)
  apps/web/                   ← Next.js
  services/api/               ← FastAPI app
  services/worker/            ← scheduler + jobs
  packages/core/              ← edgefront_core (settings, db, models, logs, parsers, utils)
    src/edgefront_core/migrations/  ← Alembic; apply with `python -m edgefront_core.migrate`
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
- **Verified 2026-11-24 (Phase 2):**
  - `GET /api/data/metar?ids=K…,K…&format=json&hours=N` works as described. JSON fields used: `rawOb`, `obsTime` (epoch s), `metarType` (METAR/SPECI), `receiptTime`; we decode `rawOb` ourselves and use aviationweather's decoded fields only to test the parser.
  - **The response is capped at 400 reports** (newest first). A 28-station × 36 h request silently returned only ~13 h. The worker therefore plans batches (`plan_batches`: ≈ 1.6 reports/h/station, ≤ 300 per request; 36 h backfill = 6 requests of 5 stations; routine 3 h poll = 1 request) and splits any batch that still hits the cap.
  - **Once a COR exists, only the corrected report is returned**, never the original. The 3-min poller normally stores the original first; the COR row then gets `corrects_report_id` and replaces it everywhere (effective-report rule, §6.3).
  - Real reports include: a **missing wind group** (`KNYC 241451Z AUTO 10SM CLR …`), `SLPNO`, `FEW000`, `1 1/4SM`, `COR` on SPECIs, and SPECIs without a T group (whole-degree only).

### 4.2 Daily summaries: NWS Daily Climate Report (CLI) + ASOS Daily Summary (DSM) — Phase 3
- **What:** NWS text product type `DSM`, issued by each station's ASOS several times a day. It gives max/min temperature **with times**, precipitation and peak wind for the climate day (midnight–midnight **local standard time**), and catches peaks between hourly METARs.
- **Source:** api.weather.gov products endpoints, e.g. `/products/types/DSM/locations/{LOC}` then `/products/{id}`. `{LOC}` is the 3-letter product location; it is often the station ID without "K" but **not always**, so it lives in the registry as `dsm_location`.
- **Verified 2026-11-24 (Phase 1) — coverage problem, see Q14:**
  - `/products/types/DSM/locations` lists only **164** locations nationwide. Of our 28 stations only **NYC, MSP, SAT** have current DSMs there (each product's text starts `KNYC DS …` / `KMSP DS …` / `KSAT DS …`). The other 25 return an empty `@graph`.
  - NOAA tgftp (`https://tgftp.nws.noaa.gov/data/raw/cx/cxusNN.kOOO.dsm.lll.txt`) has files for 20 of the 28, but all except NYC/MSP/SAT are stale (last updated between 2008 and Oct 2026); BOS, ATL, CLT, DTW, OKC, DAL, HOU, BKF have no DSM file at all.
  - A DSM is a one-line coded product per station, e.g. `KNYC DS COR 19/11 641502/ 460700// 64/ 46//0312359/00/…`. Products can be `COR` corrections of older days (the 05:30Z NYC product on 11/24 corrected 19/11).
  - Discovery code: `edgefront_core.enrich_stations` (writes `dsm_location` only when the latest product names the station and is ≤ 7 days old).
- **Coverage check 2026-11-24 (end of Phase 2, Q14; full table `docs/coverage/2026-11-24_dsm_cli.md`, tool `tools/coverage_dsm_cli.py`):**
  - **NWS does issue current DSMs for 27 of 28 stations** (not KBKF). 24 of them are transmitted only under WMO heading **CDUS27** by the ARTCCs (`KZNY`, `KZTL`, `KZAU`, `KZFW`, …), which api.weather.gov does not carry; NYC/MSP/SAT also go out as CXUS4x from the WFO, which is why only those three appear there. Some CDUS27 copies have no WMO header in the text and use the intra-day form `KLGA DS 0700 24/11 …`.
  - **CLI (Daily Climate Report) is current on api.weather.gov for 26 of 28** (`/products/types/CLI/locations/{id without K}`, WMO CDUS4x from the WFO). None current for **KDAL** and **KBKF**.
  - So for Phase 3: CLI from api.weather.gov (26 stations) + DSM from api.weather.gov (3 stations) are production sources today. The other 24 DSMs need a feed carrying CDUS27, e.g. our LDM with IDS|DDPLUS (Q17). IEM was used for discovery only.
- **Sources (owner Q14/Q17, built Phase 3):**
  - **CLI**: api.weather.gov `/products/types/CLI/locations/{cli_location}` → `/products/{id}` for the 26 stations with `cli_location` (not KDAL, KBKF). Job every `CLI_POLL_SECONDS` (900 s) + jitter; list requests are conditional (`If-Modified-Since` from the list's `Last-Modified`); product texts fetched only when new; 3-day lookback.
  - **DSM**: pluggable fetchers (`edgefront_core.dsm_ingest.DsmFetcher`): `nws_api` = api.weather.gov for KNYC/KMSP/KSAT; `iem` = Iowa Environmental Mesonet AFOS archive for the other 24 (`dsm_source` in `stations.yaml`; KBKF has none). IEM is used through its FastAPI: `GET https://mesonet.agron.iastate.edu/api/1/nws/afos/list.json?pil=DSM<LOC>&date=YYYY-MM-DD` (product ids + `entered` times), then `GET /api/1/nwstext/{product_id}` only for products not yet stored (lighter than `cgi-bin/afos/retrieve.py`). Job every `DSM_POLL_SECONDS` (720 s) + jitter; one list request per station per run (plus the previous UTC day on a station's first run); our real User-Agent, the same as for NWS: `EdgeFront/1.0 (getedgefront.com; <CONTACT_EMAIL>)` (owner A2, 2026-11-25: never hide our identity from an upstream); 2 s pause between IEM calls; backoff 5 s x 2^n on 429/5xx. Owner to email IEM before launch (`infra/railway.md`). NWWS-OI = optional future fetcher.
  - Each DSM source has its own health row (`dsm_nws`, `dsm_iem`). If IEM is down, stored DSMs keep being served with their issue time; `dsm_iem` turns unhealthy.
- **Parsing:** the DSM is a coded text format. **Build the decoder only from real products** saved as fixtures (several stations, several issuances incl. the next-day final). Store the raw text always. If a field can't be decoded, store null and keep the raw text; don't guess.
- **Decoders (built Phase 3 from real samples only):** `parsers/cli.py` (format note `docs/formats/cli.md`; 156 real CLIs from 26 stations decode with 0 errors) and `parsers/dsm.py` (`docs/formats/dsm.md`; 97 real DSMs, 0 errors; max/min/time/precip confirmed against the same day's CLI on 22 finals, wind/gust (mph) on 20). Undecodable fields are null + `decode_errors`; `raw_text` is always stored.
- **Display (Phase 3 API, Phase 4 UI): a "Daily summaries" block** with one row per product x day: CLI today, DSM today, CLI yesterday, DSM yesterday. Per (station, climate date) the latest **final** issuance wins (a later correction or re-issue supersedes; all are kept), else the latest intraday one. CLI `covers.kind` = `preliminary` (intraday, "valid as of") | `final`; DSM = `so_far` (issue time `DS HHMM`) | `final`. Missing rows carry `status` `not_issued_yet` / `not_available` and a plain `reason`; where neither product exists (KBKF) the block says "No daily summary available for this station". IEM-sourced rows carry the attribution "DSM via Iowa Environmental Mesonet, Iowa State University".

### 4.3 NWS forecast
- **Source:** `https://api.weather.gov/points/{lat},{lon}` once per station (store office, gridX, gridY in the registry), then `/gridpoints/{office}/{x},{y}/forecast` and `/forecast/hourly`.
- **Verified 2026-11-24:** `/points` returns `properties.gridId`, `gridX`, `gridY`, `cwa`, `timeZone`, `forecast`, `forecastHourly`. We store `gridId` as `nws_office` (it is the office used in `/gridpoints`). Send coordinates with 4 decimals (NWS redirects longer ones). All 28 stations resolved; `gridId == cwa` for all.
- **Schedule:** every 30 min per station; honour `Cache-Control`/`Expires`; retry with backoff on 5xx (the API has frequent transient errors).
- **Display:** today's high (daytime period) and tonight's low, short text for Today/Tonight, a 7-slot hourly strip (temp + precip chance), issued time and office. If today's daytime period has passed, show "—" for the high rather than tomorrow's.
- **Built (Phase 3):** job every `FORECAST_POLL_SECONDS` (1800 s) + jitter. Responses carry `Cache-Control: public, max-age~3600`, `Expires`, `Last-Modified`: a station is skipped while its stored expiry is in the future, then requested with `If-Modified-Since` (304: only the expiry is extended). 5xx/429 retried with exponential backoff; one failing station never stops the others. Latest 3 forecasts per station kept (first 48 hourly periods stored).
- **Selection rules** (`parsers/forecast.py`): today's high = the daytime period whose start is today in the station's local time and that has not ended (else null, never tomorrow's); tonight's low = the first night period that has not ended and started today or earlier ("Tonight" in the afternoon, "Overnight" after midnight); hourly strip = 7 slots from the current hour in 2 h steps (a missing hour is omitted, never interpolated). The first period's start follows the issue time ("Today" can start at 11:00), so list position is never used.

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

- **PFM verified 2026-11-24:** `/products/types/PFM/locations/{office}` → latest `/products/{id}`. Each point block is a UGC line, a point-name line and a lat/lon line. UGC zone codes repeat within one product, so the registry key `pfm_point` is the **point-name line** (e.g. `Central Park-New York NY`). Offices format the lat/lon line differently: `40.78N  73.97W Elev. 16 ft` (OKX) vs `36.07N 115.16W Elev. (Average Over 2.5KM Grid Box): 2181 ft` (VEF); the parser handles both. A point is assigned only if it is ≤ 3 km from the station and no other point is within twice that distance. Result: 26/28 stations; KMIA (nearest "Miami" point 4.9 km) and KHOU (no Hobby point in PFMHGX) → "Not available for this station".
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
- Enrichment command (`python -m edgefront_core.enrich_stations`): fill `lat`, `lon`, `elevation_m`, `official_name` (from NWS `/stations/{id}`, falling back to aviationweather `https://aviationweather.gov/api/data/stationinfo?ids=…&format=json`), `nws_office`, `grid_x`, `grid_y` (from `/points`). `tz` stays as set in the YAML and is **checked** against NWS `timeZone` (all 28 match). `dsm_location` and `pfm_point` are discovered automatically but written only on clear evidence; anything doubtful is printed as a flag. Idempotent (second live run: 0 changes).
- **Names:** `name` is EdgeFront's short display name from the YAML (board rows); `official_name` is the upstream name (station page title), e.g. "New York City, Central Park". Enrichment never overwrites `name`.
- **Seed semantics** (`python -m edgefront_core.seed`, idempotent): YAML sets display fields; a null `dsm_location`/`pfm_point` never overwrites a stored value; venues in the YAML are the full truth per station (others deleted); stations missing from the YAML become `active = false`. Docker's one-shot `migrate` service runs migrate + seed.
- **Venues** carry `kind: high | low` (schema, Q10). **v1 is highs only** (Q16): every mapping is `high` and unverified; lows are a later version.
- Positions: NWS `/stations` coordinates are used. aviationweather positions differ by 1.7–3.1 km for KATL, KCLT, KDAL, KORD, KSAT (flagged, informational).

### Seed list (illustrative; ALL venue mappings unverified)
| Station | Name | TZ | Venues (unverified) |
|---|---|---|---|
| KNYC | New York · Central Park | America/New_York | Kalshi |
| KLGA | New York · LaGuardia | America/New_York | Polymarket, Robinhood |
| KBOS | Boston · Logan | America/New_York | Kalshi, Robinhood |
| KPHL | Philadelphia Intl | America/New_York | Kalshi, Robinhood |
| KDCA | Washington DC · Reagan National | America/New_York | Kalshi, Robinhood |
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
- **Built (Phase 2):** a focused parser, `edgefront_core.parsers.metar` (no python-metar dependency). Test: all 1,117 real reports in `tests/fixtures/aviationweather/metar_36h_batch*.json` decode to the same temperature, dew point, wind, gust, SLP, 6 h and 24 h max/min as aviationweather's own decoding; altimeter within ±1 hPa (they publish hPa, we store inHg as reported). Only differences: we keep `FEW000` layers. Missing groups decode to null, never 0. Weather/RVR tokens are not decoded (kept in `raw_text`).
- `raw_hash` = sha256 of the whitespace-normalised raw text. `observed_at` comes from the raw `DDHHMMZ` placed in the month of `obsTime` (they agree for every fixture report).

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
- **Implementation details (Phase 2, `edgefront_core.climate`):**
  - Climate day is half-open `[start, end)` in UTC. LST: `start = local-standard midnight`. LOCAL basis: clock midnight (23/25 h on DST change days).
  - A 6-hour group's window is the 6 h ending at the synoptic hour (00/06/12/18Z) nearest the report (ASOS sends it a few minutes before the hour); groups in reports more than 30 min from a synoptic hour are ignored. A window ending exactly at `end` is inside (Q12).
  - **Effective reports:** one per (observed_at, report_type): the latest COR if any, else the original. High so far, events, the observed chart and the "latest" report all use effective reports; `/metars` lists every row and marks replaced ones `superseded`.
  - Ties keep the earliest report. The first report *with a temperature* is the day's baseline.
  - Events are recomputed for each (station, climate day) touched by an ingest and reconciled with the table (late arrivals and CORs can add or withdraw events).

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

Built in Phase 1 as Alembic revisions `0001` (source_health) + `0002` (everything else). A test asserts the migrated schema equals the ORM models. JSON columns are JSONB on Postgres.

- `stations` (id PK `KNYC`, name, **official_name**, city, state, lat, lon, elevation_m, tz, day_basis ∈ {LST, LOCAL}, nws_office, grid_x, grid_y, dsm_location, **dsm_source** (nws_api | iem | null), **cli_location**, pfm_point, active bool, **enriched_at, enrichment_source**, created_at, updated_at)
- `station_venues` (station_id FK, venue enum[kalshi, polymarket, robinhood], **market_kind enum[high, low]**, market, settlement_source, rules_url, verified bool, verified_at) — PK (station_id, venue, **market_kind**)
- `metar_reports` (id, station_id, report_type ∈ {METAR, SPECI}, observed_at, raw_text, raw_hash (sha256), is_correction, **corrects_report_id** (FK self, nullable), temp_c, dewpt_c, temp_precision, wind_dir_deg, wind_vrb bool, wind_kt, gust_kt, vis_mi, sky jsonb, altim_inhg, slp_hpa, max6h_c, min6h_c, max24h_c, min24h_c, source, fetched_at, ingested_at) — UNIQUE (station_id, observed_at, report_type, raw_hash); index (station_id, observed_at desc)
- `daily_high_events` (id, station_id, climate_date, from_c, to_c, report_id FK, observed_at, created_at)
- `cli_products` (**Phase 3**: id, station_id, product_id UNIQUE (api.weather.gov id), issuer, wmo_header, is_correction, issued_at, climate_date, report_kind in {final, preliminary}, valid_as_of_local, max_temp_f, max_time_local, min_temp_f, min_time_local, precip_in, precip_trace, normal_high_f, normal_low_f, departure_high_f, departure_low_f, raw_text, raw_hash, decode_errors jsonb, source, fetched_at, ingested_at)
- `dsm_products` (**rebuilt Phase 3**: id, station_id, product_id UNIQUE (source-specific), source in {nws_api, iem}, issuer, wmo_header, issued_at, climate_date, report_kind in {so_far, final}, issue_key (`HHMM` LST or `FINAL`), is_correction, max_temp_f, max_time_local, min_temp_f, min_time_local, precip_in, precip_trace, peak_wind_dir/speed/time_local, peak_gust_dir/speed/time_local, wind_speed_unit (`mph`), raw_text, raw_hash (of the coded body), decode_errors jsonb, fetched_at, ingested_at) — UNIQUE (station_id, climate_date, issue_key, raw_hash)
- `nws_forecasts` (id, station_id, office, generated_at, update_time, **hourly_update_time**, periods jsonb, hourly jsonb (first 48 h), **forecast_expires_at, hourly_expires_at, forecast_last_modified, hourly_last_modified**, source, fetched_at) — keep latest 3 per station
- `model_runs` (model, cycle_time, available_at, fetched_at, status, source_url, notes) — PK (model, cycle_time)
- `model_values` (model, cycle_time, station_id, valid_time, variable, value, unit, is_computed, grid_lat, grid_lon) — PK (model, cycle_time, station_id, valid_time, variable); FK (model, cycle_time) → model_runs ON DELETE CASCADE. Source comes from the parent `model_runs` row.
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
| `GET /stations/{id}/daily-summaries` | **Phase 3** (replaces `/dsm`): `today`, `yesterday`, `times_are: LST`, `status` (ok \| none_available + message), `rows` [CLI today, DSM today, CLI yesterday, DSM yesterday] each with product, product_name, day, status (ok \| not_issued_yet \| not_available), reason, covers {date, kind}, issuer, source, source_label, attribution, product_id, issued_at, valid_as_of_local, is_correction, issuances_for_day, max_f/time, min_f/time, precip_in, precip_trace, normal_high_f/low_f + departures (CLI), peak_wind/peak_gust {dir_deg, speed_mph, time_local} (DSM), raw_text, decode_errors; `sources` |
| `GET /stations/{id}/forecast` | **Phase 3**: label `FORECAST · NWS`, status (ok \| no_data \| stale), office, update_time, fetched_at, today_high_f (null once today's daytime period ended, with `today_note`), tonight_low_f, today/tonight periods {name, start, end, temperature_f, pop_percent, short, detailed}, hourly (<= 7 slots: start, temperature_f, pop_percent, short), weather_gov_url. `/stations` rows now carry `nws_today_high_f`; `/status` lists cli, dsm_nws, dsm_iem, forecast |
| `GET /stations/{id}/models?var=temp\|dewpt\|wind\|cloud\|rh&span=today\|48h` | per model: run, available_at, points [valid_time, value]; plus observed overlay from METARs |
| `GET /feed/new-highs?limit=10` | latest daily_high_events with station names |

Add OpenAPI docs in dev only. Use ETag/`Cache-Control: max-age=30` on read endpoints.

**As built in Phase 2** (models in `services/api/src/edgefront_api/schemas.py`; OpenAPI at `/api/v1/docs` when `APP_ENV=dev`):
- Temperatures are returned as stored °C (`temp_c`, 1 decimal) **and** display °F (`temp_f`, whole, half away from zero). RH is `rh_computed` (Magnus) and labelled as computed.
- `status`: `ok` | `no_data` (nothing stored yet) | `stale` (latest effective METAR older than `STALE_METAR_MINUTES`); each response carries `source` {source, producer, last_success_at}.
- `/stations` rows include `zone_group` (by standard UTC offset: Eastern/Central/Mountain/Pacific, Q12), `std_utc_offset_minutes`, `local_time`, `climate_day` {date, basis, start, end, ends_in_minutes, elapsed_fraction}, `fresh_high`, `nws_today_high_f` (null until Phase 3). `?venue=kalshi|polymarket|robinhood`.
- `/stations/{id}/metars?hours=1..48` (default 24) lists every stored report newest first with `superseded`; `/observed?hours=6|24` returns effective reports oldest first plus `gaps` (> 90 min, never bridged). `/feed/new-highs?limit=1..50`.
- `/status` lists each source with `healthy` (last success within 3× its schedule); error text is not exposed publicly.
- Unknown station → 404; invalid parameters → 422. `Cache-Control: public, max-age=30` + strong `ETag` (304 on `If-None-Match`) on read endpoints; `/health` is `no-store`.

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
- Colours: page `#F4F5F2`; surface `#FFFFFF`; border `#DDE1DC`; hairline `#ECEFEC`; ink `#101A1C`; text-2 `#2A3533`; muted `#4A5552` / `#56625F`; brand teal `#0A6E69` (hover `#064F4B`, tint `#E6F2F1`); temperature `#C24E12`, high emphasis `#B2450D`; dew point `#1F5FA8`; RH `#6B4FA0`; wind `#0A6E69`, gust `#7FB8B4`; pressure `#3D4A47`; fresh `#1A7F4B` (halo `#DDF1E5`); stale/down amber `#B7791F` (halo `#FBEFD9`; added in Phase 0, the mockups define no stale colour); premium/lock bg `#FFF1E2` text `#8A4100`; forecast/model badge bg `#EDE8F6` text `#4B3488`; footer `#101A1C`.
- Implemented as Tailwind v4 theme tokens in `apps/web/src/app/globals.css` (e.g. `bg-page`, `text-ink`, `text-brand`, `bg-fresh`, `font-display`, `font-mono`).
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
4. **Daily summaries** (design updated 2026-11-24): a table with one row per product x day (CLI today, DSM today, CLI yesterday, DSM yesterday). Columns: product + issuer, covers (date + so far / preliminary / final), issued (Z + local), max + time, min + time, precip, normal hi/lo (CLI only), expandable raw product text. Empty rows say why ("No CLI for today yet...", "Not published for this station"); stations with neither product show "No daily summary available for this station". Footer: "Shown as published by the NWS... Some markets name one of these products as their settlement source. Check each market's rules." plus "DSM via Iowa Environmental Mesonet, Iowa State University" where IEM is the source. Data: `GET /stations/{id}/daily-summaries`.
5. **Observed conditions** chart (ECharts, shared time axis, stacked panels): toggles Temp & dew point · Humidity (computed) · Wind (sustained line + gust range bars) · Sky (METAR cover strip) · Pressure (off by default). Range 6 h / 24 h. Points at each METAR/SPECI time; **gaps where reports are missing** (no line across gaps > 90 min). Readout row for the latest METAR. Locked "5-minute data · Premium" button → `/pricing`. Tooltip shows exact values, report time and type.
6. **Hourly METAR reports**: Raw / Decoded toggle; newest first; SPECI highlighted; last 12 h with "Show all 24 hours".
7. **Model guidance**: MODEL DATA badge; variable tabs Temp / Dew pt / Wind / Cloud / RH; Today / 48 h; "Latest run per model" select (v1: latest only); model chips grouped Global (IFS, GFS) · AI (AIFS) · Statistical (GFS-MOS, NBM, LAMP) · NWS (PFM) with All/None; chart with each model's line (markers at real valid times only) + observed METAR line on top + "Now" marker. Tooltip: model, run (cycle) and received time. Footnote: reference only; EdgeFront doesn't rank or blend models. Hide GEFS spread until GEFS exists.
8. Footer as homepage, plus ECMWF CC BY 4.0 attribution.

### 10.4 Other pages
- `/pricing`: Free vs Premium comparison (§2), Premium "Coming soon" button, FAQ (what "5-minute" means, data sources, no advice).
- `/sources`: each source with producer, what we use, update cadence, licence/attribution, time-stamp definitions (observed / fetched / age), how "high so far" and the climate day work.
- `/terms`, `/privacy`: placeholder pages clearly marked "Draft — pending legal review". **Do not write legal terms.**
- 404 and per-section error/empty/stale states.

### 10.5 As built (Phase 4)
- **Data flow:** server components read FastAPI over `API_INTERNAL_URL` through `apps/web/src/lib/api.ts`: `load()` calls `await connection()` (request time only, so `next build` never contacts the API) and then a `"use cache"` fetch with `cacheLife({ stale: 30, revalidate: 60, expire: 240 })` shared across requests. A 404 is returned from the cached function as a value (errors lose their class across a `use cache` boundary); other errors are thrown and never cached. The browser never calls FastAPI: client refresh goes through thin proxies `/api/status`, `/api/stations`, `/api/stations/{id}/current` (every 60 s, paused while the tab is hidden).
- **Times:** absolute times are rendered on the server from the station's IANA zone (identical on the client); relative ages render only after mount and update every 30 s. The board's "Local day ends in" countdown is computed in the browser from the station tz (`lib/climate.ts`, same LST rule as Python), never the browser's zone.
- **Units:** one °C→°F helper (`lib/units.ts`, integer arithmetic, half away from zero) with the same test cases as Python. METAR wind kt, DSM/CLI wind mph, always labelled.
- **Search aliases** live in `stations.yaml` (`aliases:`), stored in `stations.aliases` (migration 0004) and returned by `/stations`.
- `/station/kdfw` → 308 → `/station/KDFW` (`src/proxy.ts`). Unknown stations render the friendly not-found page (see Q21 about its HTTP status).
- SEO: per-station title/description/canonical/OpenGraph, `sitemap.xml` (request-time, all stations), `robots.txt`. No analytics.
- Tests: Vitest (39) for rounding, climate countdown incl. DST and the 1:00 AM case, relative age, search, state mapping, gaps; Playwright (13 tests × 1440/375 px) on the live stack. Lighthouse (production build): accessibility 100 on `/` and `/station/KDFW` (mobile + desktop).

### 10.6 Deviations from the design mockups (Phase 4, with reasons)
1. "Sign in" removed from the header (owner B2: no accounts in v1). The yellow "Design mockup · sample data" banner is not shipped.
2. Hero subline lists what v1 has (METARs, CLI + DSM daily summaries, NWS forecasts); model guidance is mentioned only after Phase 5.
3. Header nav is the same on every page (Stations · Map PRO · Sources · Pricing); the mockups differed between pages. The station page's search sits at the top of the page body instead of inside the header so the header can wrap cleanly at 375 px.
4. Station title shows the NWS official name (e.g. "Dallas/Fort Worth International Airport"); the EdgeFront display name, lat/lon, elevation, ASOS, local standard time offset + IANA zone and current local time are in the mono meta line; an extra line names the venues and the "being verified" note.
5. Big numbers are 72 px on phones (96 px from `sm`), so the two cards fit at 375 px.
6. Forecast low tile uses the NWS period name ("Tonight · Low" or "Overnight · Low") instead of always "Tonight".
7. Daily summaries: the expanded row also shows the decoded DSM highest wind/gust (mph) and a note when several issuances exist for the day; corrections carry a COR tag. KBKF-type stations show one message instead of four rows.
8. Observed chart is ECharts (not the mockup's SVG): temperature/dew point plotted in whole °F (same rounding as everywhere), gusts as vertical marks from sustained wind to gust, sky strip from each report's greatest cover, "No reports" shading for gaps > 90 min. No °F/°C toggle (the mockup's unit state; v1 is °F only).
9. METAR list copy: "routine reports at the station's scheduled minute" (not ":53" — stations differ); decoded visibility comes from the report (the mockup hard-coded 10 mi).
10. Board: a small SPECI tag next to the last-report time; stale rows show the time and age in amber; "—" for no high yet (e.g. a new climate day before its first report).
11. Map teaser dots are neutral grey (the mockup used brand/orange dots that could read as data) and the copy says Premium is coming later.
12. Footer follows the owner's B2 list (sources, independence note, venue-label note, terms/privacy, "Data is provided as received…"); the station mockup's "Time stamps" column moved to `/sources` definitions; "Report a data problem" is omitted (no contact flow in v1).
13. `/pricing`, `/sources`, `/terms`, `/privacy` and 404 had no mockups; they use the same tokens and components.

---

## 11. Phases (v1)

Each phase ends with: tests passing, a short demo note, CONTEXT.md updated, and a **stop for owner review**.

| Phase | Scope | Done when |
|---|---|---|
| **0. Foundation** | Monorepo, tooling (uv, pnpm, ruff, mypy, eslint, prettier), Docker Compose (postgres/api/worker/web), `.env.example`, CI (lint + tests), `design/` + CONTEXT.md in repo | `docker compose up` gives a hello page, `/api/v1/health` ok and a worker heartbeat; CI is green |
| **1. Data model + registry** | Alembic schema (§7), `stations.yaml` seed, enrichment command, `source_health` | Seed + enrich run idempotently; 28 stations with lat/lon/tz/office/grid; unverified venues flagged |
| **2. METAR pipeline** | Fetch job, parser (§6.1) with real fixtures, dedupe/corrections, high-so-far + new-high events (§6.2–6.3), API: stations, current, metars, observed, feed, status | 24 h of real METARs for all stations; parser tests cover T-group, 6 h/24 h groups, SPECI, COR, VRB, missing fields; high-so-far correct across a DST and an LST-midnight test case |
| **3. Daily summaries (CLI + DSM) + NWS forecast** | Real CLI + DSM fixtures (≥ 8 stations each) and format notes (`docs/formats/`); CLI decoder + job (api.weather.gov, 15 min); DSM decoder + pluggable fetchers (api.weather.gov for KNYC/KMSP/KSAT, IEM for the rest; 10–15 min, polite); NWS forecast + hourly (30 min, cache headers, 5xx backoff); API: daily-summaries, forecast, board `nws_today_high_f`, status | CLI decoded for ≥ 24 of 26 stations; DSM decoded for ≥ 24 of 27; undecodable products show raw text + decode error; ≥ 2 h live run with no duplicates, a correction handled, IEM failure simulated in tests; forecast refreshes for all 28; 5xx backoff and today's-high edge cases (morning, evening, DST day) tested |
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
APP_ENV=dev                               # dev | test | prod (OpenAPI docs at /api/v1/docs only in dev)
LOG_LEVEL=INFO
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
| Q1 | ~~Contact email for the NWS User-Agent~~ **Answered 2026-11-24:** owner supplied it; it lives only in `.env` / deploy env vars (`CONTACT_EMAIL`), never in the repo | — |
| Q2 | Source of HGEFS | Not in v1 |
| Q3 | `madis-publisher` cadence (run `systemctl cat madis-publisher.service`) | Needed for Premium (v2) |
| Q5 | Pricing page: collect emails for a waitlist? | No; "Coming soon" only |
| Q6 | Verified station-to-venue list | Seed list, flagged unverified |
| Q7 | Day basis per venue (LST vs local calendar) | LST for all |
| Q8 | Premium price points | "Coming soon", no prices |
| Q9 | Ingest the NWS Daily Climate Report (CLI)? Kalshi has historically settled on it; it is not in the v1 source list. Also verify the claim that Kalshi moved to The Weather Company on 2026-08-14 | Not ingested; board footnote kept generic |
| Q10 | ~~Add `market_kind` (high/low) to `station_venues`?~~ **Answered 2026-11-24: yes, both.** Built in migration 0002 | — |
| Q11 | Phase 1 schema defaults: `metar_reports.corrects_report_id`; `source` on `nws_forecasts` (and `dsm_products`); `model_values` inherits source from `model_runs` | **Applied in Phase 1** |
| Q12 | Board time-zone groups: group by **standard UTC offset** (Detroit/Louisville → Eastern, Phoenix → Mountain); "Local day ends in" counts to LST midnight (1 AM clock time in DST). Climate day is `[start, end)`; a 6 h window ending exactly at `end` counts as inside | As stated |
| Q13 | Docker and GitHub not set up yet (owner: "later"). Phase 0's `docker compose up` and green CI are therefore unverified locally | Verified with a local non-Docker run on SQLite; CI `docker` job verifies once a remote exists |
| Q14 | ~~DSM only for 3 of 28 stations~~ **Resolved 2026-11-24 (final, Phase 3 kickoff):** Phase 3 builds **"Daily summaries"** from two NWS products: **CLI** (Daily Climate Report) from api.weather.gov for the 26 stations that have it; **DSM** (ASOS Daily Summary) from api.weather.gov for KNYC/KMSP/KSAT and from the Iowa Environmental Mesonet (IEM) for the rest (Q17). Coverage evidence: `docs/coverage/2026-11-24_dsm_cli.md` | — |
| Q15 | ~~KDCA state DC vs VA~~ **Resolved 2026-11-24:** display name stays "Washington DC · Reagan National"; official name and state stay in the station details | — |
| Q16 | ~~Low markets?~~ **Resolved 2026-11-24: v1 is highs only.** Every venue mapping stays `market_kind = high` and unverified; lows come in a later version (schema already supports them) | — |
| Q17 | ~~Can our LDM provide IDS\|DDPLUS?~~ **Resolved 2026-11-24: no.** Our LDM's only upstream is `ldm.madis.ncep.noaa.gov` (MADIS FSL2 HFMETAR only); Unidata IDD is not for commercial use. **DSM source for the other 24 stations = IEM AFOS text archive** (mirrors the NWS text stream; owner confirmed current DSMs, e.g. `pil=DSMDFW`). IEM terms: data described as public domain, usable "for any lawful purpose", no warranty, attribution appreciated → **we attribute** ("DSM via Iowa Environmental Mesonet, Iowa State University"). tgftp dropped. **Optional future upgrade: NWWS-OI** (NOAA Weather Wire Service – Open Interface, free push service, sign-up required) as another DSM/CLI fetcher | — |
| Q18 | ~~KBKF on the board?~~ **Resolved 2026-11-24:** keep KBKF on the board; show it stale when it is | — |
| Q19 | ~~KDAL / KBKF without daily summaries~~ **Resolved 2026-11-24:** OK. Where neither product exists the block says "No daily summary available for this station" | — |
| Q20 | ~~KZFW finals for KDFW/KDAL/KOKC?~~ **Resolved 2026-11-25 (live run):** KZFW's finals do arrive (11-22 and 11-24 finals both entered at 06:16Z next morning for all three). Only the **11-23 finals were never issued** by KZFW — a one-off gap at the source. The block keeps showing that day's latest intraday DSM, labelled "so far" | — |
| Q21 | Unknown station URLs (e.g. `/station/KZZZ`) show the friendly not-found page but return **HTTP 200** (Next streams it from inside the page's Suspense boundary and adds `noindex`). A true 404 needs the station list in `proxy.ts` (e.g. a small cached list or a build-time env var). Worth doing? | Accept 200 + noindex for v1 |
| Q22 | Local verification on **Postgres**: the Postgres-only tests and CI job are written, but no Postgres runs on the dev machine and there is no GitHub remote yet. Approve downloading the official PostgreSQL Windows binaries locally, install Postgres/Docker, or add the GitHub remote so CI runs? | Tests run on SQLite locally; 12 Postgres-only tests skip |
| Q23 | The local live worker dies whenever the dev session ends (three interrupted runs). For the record: it is now started as a detached process for local runs; on Railway the worker is its own service | — |

## 15. Progress log
- 2026-11-24 — Plan written. Designs: homepage + free-tier station page. Phase 0 not started.
- 2026-11-24 — Owner decision: 5-minute HFMETAR is Premium only and is **not built in v1** (no ingest, no table, no LDM proxy). v1 phases renumbered 0–6.
- 2026-11-24 — **Phase 0 (foundation) built** on branch `phase-0-foundation` (local git, no remote yet). Done: uv workspace (core/api/worker, Python 3.12, ruff, mypy strict, pytest); `GET /api/v1/health` (503 when DB down); worker APScheduler heartbeat every 60 s writing `source_health('worker')` + JSON logs; Alembic bootstrap migration `0001` (source_health only); Next.js 16.4 coming-soon page calling API health server-side; tokens + fonts; Vitest + Playwright placeholder; Dockerfiles (Debian slim) + `infra/docker-compose.yml` with one-shot `migrate`; GitHub Actions CI. Verified locally without Docker (SQLite). Left: run `docker compose up` and CI once Docker/GitHub exist (Q13); owner answers Q1, Q9, Q10.
- 2026-11-24 — **Phase 1 (data model + registry) built** on branch `phase-1-registry`. Done: migration `0002` with all §7 tables except `hf_observations` (+ `market_kind`, `corrects_report_id`, `official_name`, `source` columns); `data/stations.yaml` (28 stations, 46 venue mappings, all unverified, all `high`); idempotent `seed`; `enrich_stations` with live-verified sources (aviationweather stationinfo, NWS `/stations`, `/points`, DSM + PFM product discovery); shared upstream HTTP client with retries; fixture-capture CLI (`python -m edgefront_core.fixtures`); 14 real fixtures. Live result: 28/28 stations with lat/lon/elevation/office/grid, tz verified, `dsm_location` 3/28, `pfm_point` 26/28. Key finding: DSM coverage (Q14). Left: Q14, Q15, Q16; Docker/CI still unverified (Q13).
- 2026-11-24 — Phase 1 approved and merged to `main`. Owner decisions: Q14 resolved ((b)+(a)+coverage check), Q15 (KDCA display name), Q16 (highs only); Q17 added.
- 2026-11-24 — **Phase 2 (METAR pipeline) built** on branch `phase-2-metar`. Done: focused METAR parser validated on 1,117 real reports; batched fetch with the newly found **400-report cap** handled; worker job every 180 s with 36 h backfill; dedupe, COR linking; climate day (LST/LOCAL), high so far with the 6 h-group rule, new-high events reconciled at ingest; API `/stations`, `/stations/{id}`, `/current`, `/metars`, `/observed`, `/feed/new-highs`, `/status` with ETag/caching. Live run: 1,118 reports for 28/28 stations (24–29 METARs per station in 24 h), 0 parse errors, 189 events; second poll all duplicates. DSM/CLI coverage check delivered (`docs/coverage/2026-11-24_dsm_cli.md`). Left: Q17–Q19; Docker/CI still unverified (Q13).
- 2026-11-24 — Phase 2 approved and merged to `main`. Owner decisions Q14–Q19 resolved (CLI + DSM daily summaries; DSM via IEM for 24 stations; highs only; KBKF stays; KDAL/KBKF empty states).
- 2026-11-24 — **Phase 3 (Daily summaries + NWS forecast) built** on branch `phase-3-daily-forecast`. Done: real fixtures (23 CLIs / 13 stations; 40 IEM DSMs / 15 stations; 12 NWS DSMs; forecasts for 3 stations); CLI + DSM decoders built only from samples, with format notes (`docs/formats/`); CLI ingest (api.weather.gov), DSM ingest with pluggable fetchers (api.weather.gov, IEM FastAPI), NWS forecast ingest (Cache-Control/Expires/If-Modified-Since, 5xx backoff); migration 0003; API `/stations/{id}/daily-summaries`, `/stations/{id}/forecast`, board `nws_today_high_f`, new `/status` sources; 235 tests. First live pass (17:39–17:47Z): CLI 26/26 stations decoded (197 products, 0 decode errors), DSM 27/27 (171 products: 42 NWS + 129 IEM, 0 decode errors, 2 duplicate transmissions skipped), forecast 28/28, 0 duplicates, 0 warnings/errors. Sample responses: `docs/api-samples/phase3/`.
  - **Live-run check: IN PROGRESS** (owner chose not to wait). First run 2026-11-24 17:39Z–17:58Z on a local SQLite DB was **cut short after 19 min** when the dev session ended (the local worker is tied to the session; no errors before that). Restarted 2026-11-25 ~06:48Z on the same DB for 2 h 10 min; it also catches up the ~13 h gap (overnight CLI/DSM finals). Results (products picked up during the run, duplicates, decode errors, IEM/NWS errors, forecast 304/skip behaviour, Q20) to be reported at the start of the Phase 4 report.
- 2026-11-25 — Phase 3 approved and merged to `main`. Phase 4 started on `phase-4-frontend`.
- 2026-11-25 — **A2:** IEM requests now send the real EdgeFront User-Agent incl. CONTACT_EMAIL (test pins it). **A3:** Postgres sessions pinned to `timezone=UTC`; Postgres-only tests (timestamptz, jsonb, enums, constraints, cascades, migrations down/up) + CI `REQUIRE_POSTGRES` guard + explicit migrate up/down/up step; not yet run on Postgres locally (Q22). Migration 0004 (`stations.aliases`); 0005 fixes JSON columns storing the literal `'null'` instead of SQL NULL (made every product look like it had decode errors).
- 2026-11-25 — **Phase 4 (website) built**: `/`, `/station/[id]`, `/pricing`, `/sources`, `/terms`, `/privacy`, 404, sitemap/robots; shared state components; ECharts observed chart; Vitest 39, Playwright 26 (13 × 2 widths), Lighthouse a11y 100. Every UI state seen on screen against degraded backends (API down, empty DB, day-old DB, slow API). Live run (worker on A2 code) running detached 08:42Z–~10:52Z; results so far in the Phase 4 report.
