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

> **Superseded by v2 §V2.3 (tiers) for v2.** v1 as deployed still follows this section.

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

~~v1 has no accounts, no payments and no auth~~ (**superseded by v2**: accounts in Phase 7, payments in Phase 8). In v1 as deployed: v1 has **no accounts, no payments and no auth**. Premium elements appear as locked buttons that link to `/pricing`. The pricing page lists Premium features with a **"Coming soon"** state. It does not collect emails (open question Q5).

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
- **PostgreSQL**: Railway Postgres (plain Postgres **18.7**, Railway's template; CI and the backup image pin `postgres:18.7-bookworm`; TimescaleDB is not needed at this data volume). Watch the **5 GB volume cap** (§9 retention).
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
| **LAMP** | NWS MDL | NOMADS `lmp` LAV text bulletins (`lmp.tHH30z.lavtxt.ascii`, verified Phase 5; `lmp_lavtxt.tCCCCz` does not exist), hourly 1–25 h | Text | The design calls this "GLMP"; v1 uses **station LAMP** and labels it **LAMP** |
| **PFM** | NWS forecast office | api.weather.gov products type `PFM` for the station's office; parse the block for the station's point | Text | Not every station has a PFM point: nullable |
| **GFS** | NOAA/NCEP | NOAA AWS open-data bucket or NOMADS, via Herbie (byte-range downloads of only the needed fields using `.idx`) | GRIB2 0.25° | Fields: TMP 2 m, DPT 2 m, UGRD/VGRD 10 m, TCDC; hourly to 54 h |
| **IFS** | ECMWF | ECMWF open data via `ecmwf-opendata` (or AWS mirror) | GRIB2 0.25° | Params `2t`, `2d`, `10u`, `10v`, `tcc`. Licence **CC BY 4.0, attribution required** |
| **AIFS** | ECMWF | ECMWF open data, `model="aifs-single"` | GRIB2 0.25° | Different file naming from IFS: use the package. CC BY 4.0 |

- **PFM verified 2026-11-24:** `/products/types/PFM/locations/{office}` → latest `/products/{id}`. Each point block is a UGC line, a point-name line and a lat/lon line. UGC zone codes repeat within one product, so the registry key `pfm_point` is the **point-name line** (e.g. `Central Park-New York NY`). Offices format the lat/lon line differently: `40.78N  73.97W Elev. 16 ft` (OKX) vs `36.07N 115.16W Elev. (Average Over 2.5KM Grid Box): 2181 ft` (VEF); the parser handles both. A point is assigned only if it is ≤ 3 km from the station and no other point is within twice that distance. Result: 26/28 stations; KMIA (nearest "Miami" point 4.9 km) and KHOU (no Hobby point in PFMHGX) → "Not available for this station".
- **Verified + built in Phase 5 (2026-11-25)** — format notes `docs/formats/model_text.md`, `pfm.md`, `grib.md`; spot checks + memory `docs/verification/models.md`:
  - **Text bulletins (NOMADS):** NBH `blend/prod/blend.YYYYMMDD/HH/text/blend_nbhtx.tHHz` (~28 MB, hourly, 25 hourly columns), NBS `…/blend_nbstx.tHHz` (~29 MB, 3-hourly to ~72 h, `FHR` row), MAV `gfs_mos/prod/gfs_mos.YYYYMMDD/mdl_gfsmav.tHHz` (3.6 MB, 00/06/12/18), LAV `lmp/prod/lmp.YYYYMMDD/lmp.tHH30z.lavtxt.ascii` (4.6 MB; only the **HH30** issuance is the full 25 h bulletin — HH00/15/45 carry CIG/VIS only). All 28 stations are in all four. NBM in EdgeFront = NBH hourly, then NBS beyond NBH's last hour, as **one run**. Units: TMP/DPT °F (first-hour bias vs METAR ≈ 0 °F at 28 stations), WSP kt (fits kt better than mph for LAMP/NBH; MDL documentation pages refuse automated fetches — Q24), SKY % (NBM), CLD categories CL/FW/SC/BK/OV (MAV, LAV). No RH in any bulletin → computed (flagged).
  - **PFM:** decoder reads the 3-hourly section only (Temp, Dewpt, **RH (own)**, Wind spd **mph**, Clouds CL/FW/SC/**B1/B2**/OV). The matrix does not start at the issue time (VEF 10:32 PM issuance starts at 1 PM that day): valid times come from the Date row + local-hour row, checked against the UTC row. Three lat/lon line formats seen. Runs are keyed per office (`issuer`), because two offices can issue in the same minute (GSP and PSR both 11:01Z).
  - **GRIB:** GFS 0.25° from the NOAA bucket on AWS (NOMADS fallback; NOMADS published f006 16 min earlier), fields TMP/DPT/**RH (own)** 2 m, UGRD/VGRD 10 m, instantaneous TCDC (not the 6 h average), LAND + HGT at f000; f000–f054 hourly (~5.3 MB/step, ~290 MB/run). IFS (`2t 2d 10u 10v tcc`, lsm every step, z at step 0; 3-hourly; tcc as **fraction**) and AIFS single (same params, 6-hourly; tcc in **%**), URLs `data.ecmwf.int/forecasts/YYYYMMDD/HHz/{ifs|aifs-single}/0p25/oper/…` (06/18Z also `oper`). One Range request per message via EdgeFront's own client. **Deviation:** Herbie / ecmwf-opendata were used to verify layouts but not for transfers (default `python-requests` User-Agent; Herbie also probes a Utah mirror) — owner A2.
  - **Space/time:** nearest grid point with land fraction ≥ 0.5 within 4 cells, from the run's own mask; stored grid lat/lon, distance, land fraction, model height. Native valid times only; partial runs are stored step by step (`status partial`, `steps_fetched/steps_expected`). Every GRIB message's date/time/step is checked against the run.
  - **Spot checks:** 82/82 match (GFS vs NOMADS GRIB filter; IFS/AIFS vs cfgrib+xarray; text vs raw bulletins). **GRIB peak RSS per job:** AIFS 142 MB, IFS 145 MB, GFS 144 MB (< 1 GB).
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
- Store temperatures in °C (numeric(4,1)). Convert to °F only for display, rounded to whole °F with the NWS rule (FMH-1 §2.6.3: .5 rounds up, floor(x+0.5); **changed from "half away from zero" in v2 Phase 9**). Show °F everywhere in v1 (U.S. traders); there is no unit toggle.
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
- Cloud categories map to midpoints for plotting only, with the category shown in tooltips:

| Product | Codes → plotted % | Basis |
|---|---|---|
| METAR (observed), GFS-MOS, LAMP | CLR/CL 0, FEW/FW 19, SCT/SC 44, BKN/BK 75, OVC/OV 100 | octa midpoints |
| **PFM** (Phase 6, owner Q25) | CL 2.5, FW 15, SC 37.5, **B1 59.5**, **B2 78**, OV 93.5 | midpoints of the PFM's own ranges (NWS PFM Product Specifications, Table 2: CL 0–5 %, FW >5–25 %, SC >25–50 %, B1 >50–69 %, B2 >69–87 %, OV >87–100 %); the tooltip shows code + range |

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
- `model_runs` (**rebuilt Phase 5, migration 0006**: id PK, model, cycle_time, **issuer** ('' or the PFM office), available_at (first seen), fetched_at, updated_at, status ∈ {partial, complete, failed}, source_url, steps_expected, steps_fetched, notes) — UNIQUE (model, cycle_time, issuer)
- `model_run_stations` (**Phase 5**: run_id FK CASCADE, station_id, status ∈ {ok, not_available, failed}, reason, point_name, grid_lat, grid_lon, grid_distance_km, height_m, land_fraction) — PK (run_id, station_id)
- `model_values` (**Phase 5**: run_id FK CASCADE, station_id, valid_time, variable ∈ {temp, dewpt, wind, cloud, rh}, value + unit canonical (degC, kt, pct, category), native_value, native_unit (degF, K, mph, m/s, fraction, pct, category), category (cloud code), is_computed) — PK (run_id, station_id, valid_time, variable). Source comes from the parent `model_runs` row.
- `hf_observations` (**v2, do not create in v1**) (station_id, observed_at, temp_c, dewpt_c, wind_dir_deg, wind_kt, gust_kt, altim_pa, vis_m, qc jsonb, file_name, file_modified_at, ingested_at) — PK (station_id, observed_at)
- `source_health` (source PK, last_success_at, last_attempt_at, last_error_at, last_error, last_item_time, notes)
- **v2 Phase 7, migration 0007: schema `auth`** (Better Auth 1.7.28's tables, camelCase columns exactly as Better Auth generates them; on SQLite the same tables without a schema): `user` (id text PK, name, email UNIQUE, emailVerified, image (always NULL), createdAt, updatedAt), `session` (id, expiresAt, token UNIQUE, createdAt, updatedAt, ipAddress, userAgent, userId FK→user CASCADE; index userId), `account` (id, accountId, providerId, userId FK CASCADE, accessToken/refreshToken/idToken + expiries (always NULL: not stored), scope, password (scrypt hash), createdAt, updatedAt; index userId), `verification` (id, identifier (index), value, expiresAt, createdAt, updatedAt), `rateLimit` (id, key UNIQUE, count, lastRequest bigint ms). Alembic owns the DDL (Better Auth never migrates); `auth_schema.include_object` keeps these tables out of the ORM model diff; CI's `auth` job runs `apps/web/scripts/auth-schema-check.mjs` (Better Auth's own migration planner must find nothing to add). Personal data: `docs/privacy-data-inventory.md`.
- **v2 Phase 8, migration 0008: schema `billing`** (Stripe mirror, owned by the web app, no ORM models; same `include_object` exclusion; CI checks it with `apps/web/scripts/billing-schema-check.mjs`): `customers` (user_id PK FK→auth.user CASCADE, stripe_customer_id UNIQUE, trial_used_at, created_at), `subscriptions` (stripe_subscription_id PK, user_id FK CASCADE (index), stripe_customer_id, status, price_id, current_period_end, cancel_at_period_end bool, cancel_at, trial_end, canceled_at, ended_at, latest_invoice_status, updated_from_event_id, updated_at), `webhook_events` (stripe_event_id PK, type, received_at, processed_at, error). SQLite: same tables in the main DB, ISO text times, 0/1 booleans.

---

## 8. Public API (FastAPI, read-only, `/api/v1`)

All responses include `generated_at` and, per block, `source` + times. Errors distinguish "no data yet" (200, `status: "no_data"`) from "upstream down" (`status: "stale"` with `last_success_at`).

**v2:** `/api/v1/internal/*` is for the web server only (Premium data from Phase 9): it requires header `X-Internal-Token` = `INTERNAL_API_TOKEN` (constant-time compare) and fails closed with 403 when the token is unset. Phase 7: `GET /api/v1/internal/ping`. Phase 9 adds `GET /api/v1/internal/stations/{id}/hf?hours=6|24`, `/stations/{id}/hf-current` and `/map` (5-minute data, `Cache-Control: private, no-store`). Accounts live in the web app (`/api/auth/*`, Better Auth), not in FastAPI.

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
| `GET /stations/{id}/models?var=temp\|dewpt\|wind\|cloud\|rh&span=today\|48h` | **Phase 5**: `window` {span, start, end (UTC), start_local, end_local (LST offset), climate_date, basis}, `now`, `unit` (degF \| kt \| pct), `observed` {source, points} (effective METARs in the window up to now: whole °F / kt / computed RH / greatest cover → midpoint + category), `models[]` (IFS, GFS, AIFS, GFS-MOS, NBM, LAMP, PFM): id, label, group, producer, colour_token, licence, available + reason + reason_code (no_run \| no_station \| no_variable \| station_failed), kind (continuous \| categorical), native_unit, native_step_hours, run {cycle_time, issuer, available_at, fetched_at, status, steps_expected, steps_fetched, source_url, stale (> 2× cycle interval since received)}, grid {lat, lon, distance_km, height_m, point_name}, points [valid_time, value (display unit; categorical → §6.5 midpoint), category, is_computed]. Latest run per model that has the station; PFM by the station's office. `/status` gains one `model_*` entry per model |
| `GET /feed/new-highs?limit=10` | latest daily_high_events with station names |

Add OpenAPI docs in dev only. Use ETag/`Cache-Control: max-age=30` on read endpoints.

**As built in Phase 2** (models in `services/api/src/edgefront_api/schemas.py`; OpenAPI at `/api/v1/docs` when `APP_ENV=dev`):
- Temperatures are returned as stored °C (`temp_c`, 1 decimal) **and** display °F (`temp_f`, whole, NWS half-up rounding; v2 Phase 9 adds the structured `temp` object with `f_exact`, `f_rounded`, `f_possible`). RH is `rh_computed` (Magnus) and labelled as computed.
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
1. Header: logo (front-line mark + "EdgeFront"), nav: Stations · Map (PRO lock pill → `/pricing`) · Pricing · Sign in (disabled/"coming soon" in v1; **superseded by v2 §V2.2 Header**: Sign in + Start free trial / avatar menu with FREE·PREMIUM badge).
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
- **Units:** one °C→°F helper (`lib/units.ts`, integer arithmetic, NWS half-up since v2 Phase 9) with the same test cases as Python (shared file `packages/core/tests/fixtures/temp_cases.json`). METAR wind kt, DSM/CLI wind mph, always labelled.
- **Search aliases** live in `stations.yaml` (`aliases:`), stored in `stations.aliases` (migration 0004) and returned by `/stations`.
- **Station URLs (`src/proxy.ts`, owner A4/Q21):** known id in lower case → 308 to upper case; unknown id → the friendly not-found page with a **real HTTP 404**. With Cache Components the page always streams its prerendered shell with 200 and `dynamicParams` is unavailable, so the check runs in `proxy.ts` against `src/generated/stations.json` — copied from `data/stations.yaml` by `scripts/gen-stations.mjs` before every dev/build/typecheck (owner choice, 2026-11-25; not a hand-kept list). `generateStaticParams` prerenders every station: API first (2 s), else the same registry copy, so the build never depends on the API. Adding a station = edit `stations.yaml` + rebuild web.
- SEO: per-station title/description/canonical/OpenGraph, `sitemap.xml` (request-time, all stations), `robots.txt`. No analytics.
- Tests: Vitest (39) for rounding, climate countdown incl. DST and the 1:00 AM case, relative age, search, state mapping, gaps; Playwright (13 tests × 1440/375 px) on the live stack. Lighthouse (production build): accessibility 100 on `/` and `/station/KDFW` (mobile + desktop).

### 10.7 As built (Phase 5): model guidance (station section 7)
- `components/station/ModelGuidance.tsx` + pure helpers `models.ts` (Vitest). The server renders the default view (temp · Today) so run lines and the text summary are in the HTML; the client applies the URL state (`mvar`, `mspan`, `mhide`) and refetches through `/api/stations/{id}/models` (5-min refresh while visible). ECharts is imported only in the browser (lazy, as the observed chart).
- Header "Model guidance for {display name}" + MODEL DATA badge + subline; Variable tabs; Today / 48 h; static "Latest run per model"; chips grouped Global · AI · Statistical · NWS with All/None; unavailable chips are `aria-disabled` with the reason as a tooltip on hover/focus ("no {variable}" or "not available").
- Chart: one line per visible model with a **distinct marker shape** per model at its real valid times; a line breaks where the gap exceeds 2× the product's longest native step; categorical cloud drawn as steps at the §6.5 midpoints; observed METAR line in ink, 3 px; past shaded; dashed "Now" marker. Tooltip: model + producer, run + issuer, received (Z), valid time Z + local, value (category name, computed flag), native unit, grid/point distance.
- Below: text summary (also the chart's accessible name), one run line per model (run, received, partial steps, grid distance + model height, amber "stale"), footnote (reference only, no ranking/blending, native valid times, nearest land point, category midpoints, ECMWF CC BY 4.0 attribution, window in Z and local standard time).
- Homepage: hero lists the models; data status strip "Models in: IFS 06Z · GFS 06Z · …" (amber when unhealthy). `/sources`: four model source cards with live status + a "Model guidance" definition; the footer on station and sources pages carries the ECMWF attribution.

### 10.6 Deviations from the design mockups (Phase 4, with reasons)
1. "Sign in" removed from the header (owner B2: no accounts in v1; **superseded by v2**, Phase 7 adds it back). The yellow "Design mockup · sample data" banner is not shipped.
2. Hero subline lists what v1 has (METARs, CLI + DSM daily summaries, NWS forecasts); model guidance is mentioned only after Phase 5.
3. Header nav is the same on every page (Stations · Map PRO · Sources · Pricing); the mockups differed between pages. The station page's search sits at the top of the page body instead of inside the header so the header can wrap cleanly at 375 px.
4. ~~Station title showed the NWS official name~~ **Reverted (owner A3, 2026-11-25):** the title is the EdgeFront **display name** from `stations.yaml` (Q15, e.g. "Washington DC · Reagan National"); the NWS official name is in the mono meta line with lat/lon, elevation, ASOS, local standard time offset + IANA zone and current local time; an extra line names the venues and the "being verified" note.
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

### 11.2 Phase 6 performance (B1) — local production build, Lighthouse mobile, median of 3, no worker running
| Page | Before (perf / LCP / TBT / JS) | After |
|---|---|---|
| `/station/KDFW` | 71 / 3.99 s / 665 ms / 527 KiB | 93 / 2.64 s / 187 ms / 178 KiB |
| `/` | 90 / 2.92 s / 266 ms / 177 KiB | 92 / 2.81 s / 202 ms / 157 KiB |

Changes kept: ECharts (both charts) loads only when the chart is within 300 px of the viewport; self-hosted subset fonts (101 → 70 KB, same three families); below-the-fold station sections stream in their own Suspense boundaries and use `content-visibility: auto`. Tried and reverted: not preloading two fonts (FCP worse, CLS 0.10), `inlineCss` (LCP worse). A near-static page (`/pricing`) measures 3.1 s with Google's fonts and 2.4 s with no web fonts: the remaining floor is Next/React's ~117 KiB runtime plus fonts on localhost HTTP/1.1. The B9 target (< 2.5 s) is re-measured on the production URL (HTTP/2).

### 11.1 Targets carried into later phases
- **Phase 6 performance target (owner, 2026-11-25):** `/station/[id]` on mobile LCP < 2.5 s (Phase 4 measured Performance 72, LCP 3.9 s). ECharts stays lazy-loaded, and the model chart is lazy-loaded too.

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
# Phase 6
DB_SIZE_WARN_BYTES=3221225472            # worker: nightly retention warns above 3 GB
WORKER_UPSTREAM_ENABLED=true             # worker: false only in CI's Docker smoke test
INDEXING_ENABLED=false                   # web: true only after the owner's "go live"
CSP_MODE=report-only                     # web: report-only | enforce
HSTS_ENABLED=false                       # web: true once getedgefront.com serves HTTPS
RATE_LIMIT_PER_MINUTE=120                # web: per-IP limit on /api/*
BACKUP_S3_ENDPOINT / _BUCKET / _ACCESS_KEY_ID / _SECRET_ACCESS_KEY / _REGION, BACKUP_PREFIX  # backup service
# v2 Phase 7 (accounts) — web unless noted; owner steps in infra/auth-setup.md
DATABASE_URL (web too)                   # web reads/writes only schema `auth` (search_path=auth)
BETTER_AUTH_SECRET=                      # 🔒 signs sessions + email links
BETTER_AUTH_URL=http://localhost:3000    # public origin
GOOGLE_CLIENT_ID= / GOOGLE_CLIENT_SECRET=  # 🔒 secret; Google button hidden when unset
RESEND_API_KEY=                          # 🔒 unset locally → console; on Railway unset = error, never console
EMAIL_FROM=EdgeFront <no-reply@getedgefront.com>
INTERNAL_API_TOKEN=                      # 🔒 web + api, same value
AUTH_EXTRA_TRUSTED_ORIGINS=              # optional
# tests only, never on Railway: EMAIL_OUTBOX_FILE, E2E_FAKE_GOOGLE_URL (refused off localhost/on Railway), AUTH_TEST_IP_LIMIT_SCALE
# v2 Phase 8 (billing, Stripe TEST mode until Phase 11) — web; owner steps in infra/stripe-setup.md
STRIPE_SECRET_KEY=                       # 🔒 sk_test_/rk_test_; live keys refused unless STRIPE_ALLOW_LIVE=true (Phase 11)
STRIPE_WEBHOOK_SECRET=                   # 🔒 whsec_
STRIPE_PRICE_ID=                         # price_ (amount shown is read from Stripe, cached 10 min)
STRIPE_PORTAL_CONFIGURATION_ID=          # bpc_
STRIPE_TAX_ENABLED=false                 # automatic_tax in Checkout
STRIPE_MANAGED_PAYMENTS=true             # Stripe/Link merchant of record (owner decision 2026-11-27); "false" opts out
BILLING_TEST_ALLOWLIST=                  # test mode only: emails / @domains allowed to start Checkout (empty = nobody)
# v2 Phase 9 (5-minute HFMETAR) — worker; owner steps in infra/ldm/README.md
HF_INGEST_ENABLED=false                  # the hfmetar job runs only when true
LDM_API_BASE_URL=                        # https://ldm.getedgefront.com (https only)
MADIS_API_TOKEN=                         # 🔒 madis-api bearer token
HF_POLL_SECONDS=60 / HF_MAX_FILES_PER_RUN=6 / HF_BACKFILL_HOURS=24 / HF_STALE_MINUTES=15 (worker alert)
HF_STATION_STALE_MINUTES=30              # api: per-station "stale" (upstream delay 12-17 min)
# tests only: E2E_FAKE_STRIPE_URL (refused off localhost/on Railway)
```
Per-service lists, secrets and Railway reference variables: `infra/railway.md` §4. `DATABASE_URL` may be Railway's `postgresql://…`; settings rewrite it to `postgresql+psycopg://`.

## V2. v2 — Premium launch (plan)

> Added 2026-11-26 from the owner's `CONTEXT_v2.md`. v1 sections stay; where v2 supersedes them it is marked there. Designs: `design/v2/` (Pricing, SignIn, Account, StationPremium, Map). Same mockup rules as v1: layout, copy, colours and states only; **never ship the sample data**.

### V2.1 Goal
Turn the free v1 site into a product with paid Premium:
1. Accounts and sign-in.
2. Payments and subscriptions.
3. 5-minute HFMETAR data for Premium.
4. A live station map for Premium.
5. "Low so far" (on both tiers).

v1 is deployed but **not launched** (`INDEXING_ENABLED=false`). The public launch happens at the end of v2.

**Every merge to `main` auto-deploys to production.** Work on phase branches; merge only after owner approval and green CI (Postgres).

### V2.2 Decisions (owner, 2026-11-26)
| Topic | Decision |
|---|---|
| Business | Registered in the USA. Payments via **Stripe** (Checkout, Billing, Customer Portal, webhooks). |
| Plan | **One** Premium plan, **$20/month** for now. The price lives in Stripe + env config (`STRIPE_PRICE_ID`), never hard-coded in UI copy. |
| Trial | **7 days, card required at start.** One trial per account. Stripe sends a reminder email before the trial ends. |
| Sign-in | **Google** + **email/password** (email verification, password reset). More providers later. |
| Auth library | **Better Auth**, inside the Next.js app. Users and sessions stored in our Postgres. |
| Email sending | **Resend** to start (verification, password reset, account notices); SES possible later. |
| User DB | The **existing Railway Postgres**, in a separate schema (`auth`, plus `billing` for our subscription mirror). Not AWS RDS. Stripe is the **source of truth** for billing; we mirror state via webhooks. |
| Sales tax | Stripe Tax configured, **collection off** until the owner registers somewhere (Florida doesn't tax SaaS; nexus elsewhere usually starts at $100k). Prices shown "in USD; sales tax may apply". |
| Low so far | **Both tiers**: free from hourly METAR, Premium from 5-minute data. |
| Header | Signed out: "Sign in" + "Start free trial". Signed in: PREMIUM/FREE badge + avatar menu (Account, Sign out). The Map PRO lock disappears for Premium users. |
| Legal | Terms and privacy must be **properly written by the owner/legal** before launch (required by Google OAuth and Stripe). Claude Code never writes legal text. |

### V2.3 Tiers (supersedes v1 §2)
| | Free (no account needed) | Premium ($20/mo, 7-day trial) |
|---|---|---|
| Hourly METAR, daily summaries, NWS forecast, model guidance | ✅ | ✅ |
| Current temp / high so far / **low so far** | From hourly METAR | From 5-minute data (METAR value shown for comparison) |
| Observed chart | Hourly METAR | 5-minute (default) + hourly METAR toggle, METAR reports marked |
| Model chart observed overlay | METAR | 5-minute |
| Live station map | 🔒 teaser | ✅ |

A signed-in user without a subscription is a free user.

### V2.4 Entitlement rules
- `premium = true` when the Stripe subscription status is `trialing` or `active`. `past_due` keeps Premium during Stripe's retry window, with a banner. `canceled` with `cancel_at_period_end` keeps Premium until the period ends. Everything else is free.
- Entitlement is computed **server-side** from our mirrored subscription row, refreshed by webhooks, and never trusted from the client.
- Premium data is only ever served after a server-side check: the browser never calls FastAPI; the Next.js server checks the session and entitlement, then calls the internal API. Premium API routes also require an internal service token header (`X-Internal-Token`), as defence in depth even on the private network.
- Free users who request Premium data get a 403 from the Next.js route and see the locked UI, never partial data.

### V2.5 5-minute HFMETAR pipeline (from v1 §4.5, now in scope)
- **Upstream:** NOAA MADIS HFMETAR via the owner's LDM (`ldm` server) → `madis-publisher` (fixed 2026-11-26: runs ~every minute, publishes the 3 newest files only when changed, keeps the source mtime, cleans up after 3 days) → `madis-api` (FastAPI, Bearer token, **127.0.0.1:8000 only**).
- **Exposure:** an HTTPS reverse proxy on the LDM server (Caddy, e.g. `ldm.getedgefront.com`) in front of `madis-api`. Claude Code writes the config and steps; the owner applies them.
- **Worker job** (`hfmetar`): poll `/api/v1/hfmetar/files` every 60–90 s; download only files whose `modified_at` changed; gunzip and parse the netCDF (**field names from a real file**, `ncdump -h`, recorded in `docs/formats/hfmetar.md`); keep registry stations only; upsert `hf_observations` keyed by (station, observed_at) with the provider QC flags; revisions update the row and store a hash.
- **Retention:** 7 days of 5-minute data.
- **Latency:** record `observed_at`, the file's `modified_at` and our `fetched_at`/`ingested_at`; publish P50/P95 age on `/status`.
- **Built (Phase 9):** tables `hf_observations` (PK station_id + observed_at; values snapped to the verified grid, whole °C; `qc` jsonb as provided plus `off_grid`; first-seen `source_file`/`file_modified_at`/`fetched_at`/`ingested_at`; `row_hash` of values; `revision` bumps only on a value change) and `hf_files` (name, modified_at, size: change detection), migration 0010; 7-day retention (files log 4 days). Worker job `hfmetar` (`edgefront_worker/hfmetar.py`, scipy netCDF reader, in memory): /health → file list → changed files newest first (max 6 per run, 24 h backfill) → upsert. QC-failed = temperature descriptor X/Q/B: stored, left out of the 5-minute high/low, counted (`excluded_qc_count`). Alerts are log lines (`hfmetar alert: ldm_health | no_new_readings`). `/status` has an `hfmetar` block (last file, last reading, P50/P95 per stage and station over 6 h, stations reporting in 30 min, rounding check) outside `sources`, so the public strip and `/api/health` are unchanged.
- **Rights check:** before charging for it, confirm MADIS's terms for redistributing HFMETAR (ASOS) data and record the verdict and source URL in `docs/sources.md`. **Done:** MADIS "1-minute ASOS", distribution category 3 (public, no restrictions); `docs/sources.md#hfmetar`.
- **Phase 9 findings (real files, 2026-11-27/28; details in `docs/formats/hfmetar.md`). Phase 10 builds on these:**
  - **Precision (Q35):** temperature and dew point are **whole °C** (8,048/8,048 values). A 5-minute value is only good to ±0.5 °C (±0.9 °F), so every Premium value shows the possible station readings (`f_possible`, e.g. 17 °C → "reading 62–63 °F") next to the rounded and unrounded °F (B9). The hourly METAR T-group (tenths °C) is more precise.
  - **Cadence:** **5 minutes** (:00, :05 … :55) at every station in the feed. MADIS calls the feed "1-minute ASOS", but the files hold 5-minute observations, so "5-minute" in the site copy is correct.
  - **°F→°C rounding check:** the 5-minute whole °C is the nearest whole °C of the station's whole-°F reading (= NWS half-up of the METAR T-group): 21/21 exact METAR/SPECI pairs in B2, then 13/13 in production in the first 10 minutes (ongoing on `/status`, `hfmetar.rounding_check`). So `f_possible` is built on a verified rule.
  - **Coverage:** 26 of 28 stations report every 5 minutes. **KNYC (Central Park) and KBKF (Buckley SFB) are not in the feed at all** (not FAA ASOS); for them Premium shows METAR values with a note. Small gaps in 26 h: KBOS 297/312, KMSP 291/312, KSEA 288/312; all others 312/312.
  - **Delay:** a reading reaches us **~13 min (P50) / ~18 min (P95)** after observation (production `/status`, 2026-11-28: fetched P50 804 s, P95 1,104 s). MADIS receives it after ~2.3 min; the rest is MADIS file production and LDM delivery, upstream of EdgeFront. So a station's 5-minute data is "stale" only after **30 min** (`HF_STATION_STALE_MINUTES`); the worker alert for no new readings at all stays at 15 min.
  - **Rewrites:** files are rewritten for ~2 h 40 min; rows are only appended and QC letters revised, measured values never changed (0 value revisions in production so far).
  - **QC:** QC-failed = temperature descriptor X/Q/B; stored, excluded from the 5-minute high/low, counted (`excluded_qc_count`).

### V2.6 Phases (v2)
| Phase | Scope | Done when |
|---|---|---|
| **7. Accounts** | Better Auth (Google + email/password), Resend emails (verify, reset), auth schema + migrations, sign-in/up/reset pages, header states, account page (profile, sign-in methods, delete), auth rate limits, session security | A user can sign up, verify, sign in with either method, link Google + password, reset the password, and delete the account; e2e tests pass; Postgres CI green |
| **8. Billing** | Stripe (test mode): product/price via config, Checkout with a 7-day trial and card required, Customer Portal, webhooks → `billing.subscriptions` mirror, entitlement service, account billing card (all 5 states), pricing page CTA, trial-ending reminder, Stripe Tax configured (collection off) | Full test-mode lifecycle: trial → active → past_due → canceled → free, each reflected within a minute; webhook signature checks; replay/idempotency tests |
| **9. 5-minute data** | LDM proxy config + steps, `hfmetar` worker job, netCDF field map, `hf_observations`, latency metrics, MADIS rights note, internal Premium API endpoints, low so far (METAR + 5-min) | 48 h of continuous 5-min data for all stations that report it; dedupe across file rewrites proven; latency on `/status` |
| **10. Premium UI + map** | Station page tiers per `design/v2/StationPremium`; observed chart 5-min/METAR; low-so-far card on both tiers; model chart overlay; live map (MapLibre + a basemap whose licence allows commercial use, chosen with the owner); gating and teasers; 60 s refresh | Free vs Premium verified by e2e at 1440/375 px; map accessible (keyboard and list alternative); Lighthouse a11y ≥ 95 |
| **11. Launch** | Stripe live mode, Google OAuth production verification, legal pages swapped in, the remaining v1 launch steps (UptimeRobot, IEM email, restore drill, HSTS, CSP enforce, indexing on), webhook failure alerts, **48 h of continuous 5-minute data for every station in the feed (moved from Phase 9, owner 2026-11-28)** | Owner says "go live" |

### V2.7 New environment variables (names only; values in Railway)
`BETTER_AUTH_SECRET`, `BETTER_AUTH_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `RESEND_API_KEY`, `EMAIL_FROM`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID`, `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` (only if needed), `INTERNAL_API_TOKEN`, `LDM_API_BASE_URL`, `MADIS_API_TOKEN`, `HF_INGEST_ENABLED`, `HF_STATION_STALE_MINUTES` (api, default 30), `NEXT_PUBLIC_MAP_STYLE_URL` (web, optional; default OpenFreeMap Positron).

### V2.8 Open items (owner)
Q31–Q34 in §14.

### V2.9 As built (Phase 7: accounts)
- **Stack:** Better Auth 1.7.28 inside Next.js (`/api/auth/*`), Kysely adapter on `pg` (Postgres, `search_path=auth`) or `node:sqlite` locally; tables from Alembic 0007 (§7). Pages `/signin` (Sign in / Create account tabs, `?mode=signup`), `/check-email`, `/verify-email`, `/reset-password`, `/account`. `getViewer()` (server) → `{user, tier: anonymous|free, sessionCreatedAt, fresh}`; never `premium` before Phase 8.
- **Passwords:** scrypt (Better Auth default), 10–128 characters (code points), refused if in a 9,978-entry common list (SecLists, MIT, 10+ chars, lowercased; server-only, checked at sign-up, reset and change).
- **No enumeration:** sign-in errors are one generic message; sign-up always shows "check your email" — for an existing address nothing is created and an "you already have an account" email is sent instead (same response shape and timing path); reset and resend always answer the same.
- **Linking:** only to verified emails (Better Auth `requireLocalEmailVerified`); Google never links to an unconfirmed password account (`account_not_linked` → explained on /signin). Last sign-in method can't be removed.
- **Sessions:** 30 days rolling (refreshed daily), HttpOnly/SameSite=Lax/Secure in prod; revoked on password reset, on password change (other devices) and by "Sign out of all devices". Deletion needs a session younger than 10 min, else the password (or Google re-auth for Google-only accounts).
- **Rate limits** (stored in `auth.rateLimit`, survive deploys): per IP — sign-in 10/min, sign-up 10/h, reset 10/h, resend 10/h, reset-confirm 20/h, change-password 10/h, delete 5/h, get-session 600/min, others 100/min; per email (SHA-256 key) — sign-in 10/15 min, sign-up 3/h, reset 3/h, resend 3/h. Generic "Too many attempts".
- **Data minimisation:** Google avatar URL and OAuth tokens are dropped before saving; logs carry no addresses, tokens or links.
- **Header:** fixed 228×40 px slot rendered blank until the client session is known (no "Sign in → avatar" flash): signed out "Sign in" + "Start free trial" (→ /pricing); signed in "FREE" + initials menu (Account, Sign out). Header-caused layout shift measured 0 on /, /pricing, /station (e2e). /pricing CTA: signed out → `/signin?next=%2Fpricing`, signed in → disabled "Coming soon" (Phase 8). `?next=` is same-site paths only (`safeNext`).
- **Deviations / notes:** no restricted DB role (infra/auth-setup.md §4: Railway manages one user; schema separation instead); no staging (real Google tested by hand on localhost while the consent screen is in Testing; revisit Phase 11); the delete-account copy is as designed and **flagged for the owner's lawyer**; Better Auth's email confirmation uses signed links (not stored) while reset tokens use `auth.verification`; the v1 home status strip used to wrap and shift the page (CLS 0.29 locally): fixed in A1, see below.
- **A1 (owner, 2026-11-27):** status strip is always one 38 px line that scrolls sideways with an edge fade (keyboard-focusable region), CLS on `/` 0.0001 (1440) / 0 (375) with fresh data, < 0.05 with stale data (Playwright check). Below 640 px the header is one 64 px row: logo, Sign in or avatar, and a **Menu** disclosure (aria-expanded/controls; focus into the panel, Esc returns focus, closes on link choice and when focus or a click leaves it; nothing trapped) holding Stations, Map PRO, Sources, Pricing and Start free trial or Account/Sign out. CI fails on any *flaky* Playwright test (`failOnFlakyTests`) and uploads traces/screenshots for failed or flaky tests. Auth flake root cause: the e2e test navigated away while the header's sign-out request was still in flight, which aborted it (session kept, /signin redirected away); fixed in the test helpers (`signOutFromMenu` waits for the signed-out header), proven with a delayed sign-out and 520/520 passes (auth spec × 20, 2 workers, no retries).

### V2.10 As built (Phase 8: billing, Stripe test mode)
- **Stripe:** stripe-node 23.2.0, API version pinned `2026-11-18.endive` (periods live on subscription items). One product "EdgeFront Premium", one monthly price ($20 USD) from `STRIPE_PRICE_ID`; the amount on the site is read from the Price (cached 10 min), never hard-coded. Setup script `apps/web/scripts/stripe-setup.mjs` (idempotent: product, price by lookup key, Customer Portal config with card update + invoices + cancel at period end and no plan/quantity changes, webhook endpoint with the 7 events); owner Dashboard steps in `infra/stripe-setup.md`.
- **Checkout** (`POST /api/billing/checkout`, server-side only, same-origin check): signed in + email confirmed + not Premium; Stripe customer created once (metadata user_id, idempotency key per user) and reused; `payment_method_collection=always`; `subscription_data.trial_period_days=7` only if the account never had a trial (`trial_used_at` or any past subscription with a trial; no card fingerprint); `client_reference_id`; success → `/account?checkout=success`, cancel → `/pricing?checkout=cancelled`; idempotency key per click; `automatic_tax` from `STRIPE_TAX_ENABLED` (false). Trial mechanism: stable `trial_period_days` (Checkout "trial offers" are private preview).
- **Success page** grants nothing: "Activating Premium…" polls `/api/me` until the webhook mirror arrives (message after 30 s).
- **Webhooks** (`POST /api/stripe/webhook`): raw-body signature check (`STRIPE_WEBHOOK_SECRET`), unsigned/forged → 400; each event id handled once (`billing.webhook_events`); the subscription is re-fetched from Stripe and its current state mirrored (order-proof); failures → 500 so Stripe retries; logs carry event ids only. Exempt from the generic `/api/*` IP limit. Our own trial reminder email on `trial_will_end`.
- **Entitlement** (`lib/billing/entitlement.ts`, unit-tested matrix): trialing/active → Premium; past_due → Premium + banner; cancel at period end / cancel_at → Premium until then; unpaid/incomplete/incomplete_expired/paused/canceled/none → Free. Computed only from `billing.subscriptions`, attached to the session by Better Auth `customSession` (header/pricing need no extra request) and to `getViewer()` (cached per request).
- **UI:** account card in the 5 design states (trialing, active, past_due with red notice + Update card, cancelled "Premium until …" + resume via portal, free with Start trial / Subscribe); card brand/last4 and amount due read live from Stripe, not stored. Pricing CTA per state (sign in → verify email with resend → checkout; Premium → "You're on Premium" + Manage billing). Header PREMIUM badge; Map PRO pill hidden for Premium (space kept: no shift); fixed bottom "payment failed" bar site-wide while past_due.
- **Delete account** cancels live subscriptions at Stripe immediately first (refuses the deletion if Stripe fails); the Stripe customer stays for invoices.
- **Tests:** unit 136; e2e (local + CI) against `e2e/fake-stripe.mjs` (hosted pages + signed webhooks): trial → Premium, portal cancel/resume, payment failure → past_due → recovery, trial used → Subscribe without trial, delete cancels, unverified email, Stripe price, endpoint refusals.
- **Real test-mode run (2026-11-27):** setup script (idempotent, verified by a re-run); Checkout with 4242 (→ trialing), 4000…0002 ("Your card was declined", nothing created), 4000 0027 6000 3184 (3-D Secure challenge → trialing); test clock: trialing → active (trial end) → past_due (failing card, real next-retry date) → recovered (invoice paid) → cancelled in the real Customer Portal (Stripe set `cancel_at`, flexible billing) → Free with the trial used. Findings: the account defaults to **Managed Payments** (owner then chose it: ON, see below); Checkout payment methods are Dashboard-managed in this API version (no `payment_method_types`).
- **Managed Payments ON (owner, 2026-11-27):** Stripe sells through Link as merchant of record (Checkout says "Sold through Link"; statements `LINK.COM* EDGEFRONT`; receipts from Link; Link support and Link website for customers; Stripe handles disputes; it may refund within 60 days in certain cases and **without EdgeFront's approval if a support escalation isn't answered within 48 h**). Prices are **tax-exclusive**: tax is added on top of $20 by billing address (owner: pricing stays **$20 + tax**); the account card shows Stripe's invoice preview total (e.g. "$21.60 ($20.00 + $1.60 tax)"), the trial email the previewed total. Product needs an eligible tax code (`txcd_10000000`, setup script `--tax-code`). Payment methods: owner wants Cards, Apple Pay, Google Pay, Link only. Managed Payments Checkout uses the three Stripe-managed "Managed Payments Configuration 1/2/3" sets, not "Default": a check on 2026-11-27 still showed `card` + `cashapp` until those are switched off. Stripe Tax stays off. Lawyer notes in `docs/privacy-data-inventory.md` §6.
- **Test-mode allowlist (owner):** while the key is a test key, only `BILLING_TEST_ALLOWLIST` emails/domains may start Checkout (server-enforced, 403 `not_available`); everyone else sees "Premium is coming soon".
- **Deviations / notes:** trial reminder "3 days before" (owner: keep Stripe's default 3; design updated to match); past_due card shows the next retry date and no "moves to Free on" date (owner: never show a date we don't know); free state shows "Card: —" for past customers (a card may remain at Stripe); local SQLite now shares one connection between auth and billing (fixes an event-loop lock deadlock).

---

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
| Q21 | ~~Unknown station URLs return 200~~ **Resolved 2026-11-25:** real 404 via `proxy.ts` reading the build-time copy of `stations.yaml` (owner chose this over an API call per request or dropping Cache Components) | — |
| Q22 | ~~Postgres verification~~ **Resolved 2026-11-25:** repo `github.com/maishu423-debug/getedgefront` (currently **public**; owner to decide). The Postgres CI job is green on `main` (run #16, `3cdd5ef`: phases 4 + 5 merged) and on `phase-6-deploy`. Local dev/tests stay on SQLite; Postgres is verified only in CI | — |
| Q24 | ~~Text-bulletin wind units~~ **Resolved 2026-11-25:** knots. MDL's MAV card: WSP = "forecasts of the 10-meter wind speed at the hour, given in knots"; LAV/NBM same MDL convention; METAR comparison kept as supporting evidence (`docs/formats/model_text.md`) | — |
| Q25 | ~~PFM B1/B2~~ **Resolved 2026-11-25:** own values. All PFM codes plot at the midpoints of the PFM spec's Table 2 ranges (B1 59.5 %, B2 78 %), code + range in the tooltip; §6.5 table | — |
| Q26 | ~~GFS source~~ **Resolved 2026-11-25:** keep AWS primary, NOMADS fallback; ~1.2 GB/day is fine. Measure the GFS job's run time on Railway (Phase 6 B8) | — |
| Q27 | ~~LAMP extended~~ **Resolved 2026-11-25:** yes. `lavtxt_ext` (HR 26–38) is part of the same LAMP run; LAMP reaches +38 h | — |
| Q28 | ~~Backups~~ **Resolved 2026-11-26:** Option A — nightly `pg_dump` (Railway cron service `backup`) to an S3-compatible private bucket the owner provides (R2 or B2), 14 daily + 8 weekly; restore drill as a manual GitHub Actions workflow (`infra/backup-restore.md`). Waiting for the bucket + keys | Bucket from owner |
| Q29 | Launch with the draft terms/privacy pages ("Draft — pending legal review") or get them written first? EdgeFront does not write legal text | Owner decision |
| Q30 | ~~IaC~~ **Resolved 2026-11-26:** no Infrastructure as Code and no Railway CLI for v1; the owner configures every service by hand from `infra/railway.md` §3 (one table with every field `railway.json` would have held) | — |
| Q31 | Terms and privacy text (legal), needed before Google OAuth verification and Stripe live mode (supersedes Q29). Must reflect that Stripe (Link) is the merchant of record for payments (notes: `docs/privacy-data-inventory.md` §6) | Owner/legal |
| Q32 | ~~Basemap provider~~ **Resolved 2026-11-28 (owner): OpenFreeMap** public instance (style `positron` by default, `NEXT_PUBLIC_MAP_STYLE_URL`) + a **bundled public-domain U.S. outline** as automatic backup (no external requests). OpenFreeMap has no SLA; the upgrade path if it becomes unreliable is a self-hosted Protomaps file on S3 | — |
| Q33 | `madis-publisher` fix applied and verified (only changed files republished, no `sort` errors) | Owner |
| Q34 | ~~KAUS 35→40 °F at 08:53Z on 2026-11-26~~ **Resolved 2026-11-26: real, not a pipeline bug.** Raw METARs: 0653Z `02/M01 … T00171006` (1.7 °C = 35 °F), 0753Z `01/M02 … T00061017` (0.6 °C = 33 °F), 0853Z `33006KT … 04/M02 … T00441022` (4.4 °C = 39.9 → 40 °F), 0953Z again `T00441022`, 1053Z `T00391028`. Both the whole-°C group (04) and the tenths group agree; the rise came with the wind picking up from calm/light to NW 6–7 kt (mixing out the night-time inversion) and held for two hours. Pipeline used the tenths value and rounded correctly (35 → 40 °F as the climate day's first two reports above 35) | — |
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
- 2026-11-25 — **Phase 4 close-out:** A1 final live run (08:42–10:52Z, A2 code): METAR 42 runs / 93 new / 3,559 dup / 0 parse errors; CLI 9 runs / 16 new; DSM IEM 11 runs / 7 new / 1 dup; DSM NWS 11 runs / 0 new; forecast 5 runs / 100 updated / 23 × 304 / 17 fresh; 0 decode errors, 0 failed stations, 1 retried IEM disconnect; JSON-`null` cleanup → 0 rows left in all 6 JSON columns. A3 title = display name. A4 real 404s via `proxy.ts` + build-time registry copy. A2 prepared (`infra/github.md`, compose `edgefront_test`); waiting on the GitHub remote and Docker.
- 2026-11-25 — **Phase 5 (models) built** on `phase-5-models` (A1, A3, A4 closed; A2 Postgres CI waiting on the GitHub URL/Docker): real fixtures (8 NOMADS bulletins, 27 PFMs, cropped GRIB 1.1 MB) + decoders (0 errors on all 28 stations); migration 0006 (`model_runs` by id + issuer, `model_run_stations`, native units); text ingest (NBM/MOS/LAMP/PFM) and GRIB ingest (GFS/IFS/AIFS, own byte ranges, nearest land point, partial runs); `/stations/{id}/models`; worker jobs `models_text` + `models_grib` (15 min + jitter), retention 4 runs; UI section 7, status strip, hero, `/sources` model cards, ECMWF attribution. Spot checks 82/82; GRIB peak RSS ≤ 145 MB.
- 2026-11-26 — **Phase 6 (deploy) in progress** on `phase-6-deploy` (from `phase-5-models`; A1 GitHub/CI still waiting for the repo URL). Done locally: B1 performance (§11.2); dual-stack API entry point (`edgefront_api.serve`), `deploy_db` pre-deploy command, Railway URL normalisation, worker Postgres advisory lock + `WORKER_UPSTREAM_ENABLED`, nightly retention job (§9) with DB-size warning, pinned base images; web security headers + CSP (report-only/enforce switch, 0 violations both ways), per-IP rate limit on `/api/*` (429 + Retry-After), `INDEXING_ENABLED` (X-Robots-Tag + robots.txt), `/api/health`, `/api/csp-report`; backup service + restore-drill workflow; CI audit job, bundle secret check, Postgres 17; ECharts 6.1.0 (GHSA-fgmj-fm8m-jvvx). Railway itself not created yet (owner clicks, `infra/railway.md`).
- 2026-11-25 — **Phases 4 and 5 merged into `main`** after the first real CI runs. Postgres-only failures fixed: worker advisory lock kept on a pooled connection (now explicit unlock + invalidate), test station not flushed before child rows, bad-enum error class; Docker smoke test runs the worker heartbeat-only (`WORKER_UPSTREAM_ENABLED=false`, CI never contacts upstream). CI publishes failing tests/service logs as annotations. `main` run #15 (phase 4) and #16 (phase 5) green.
- 2026-11-26 — **Owner decisions:** the 48-hour production health run before review is **dropped** (launch checklist item B9-1 waived); `phase-6-deploy` merged into `main` (fast-forward to `915b0a1`, CI green) so Railway builds every service from `main` as `infra/railway.md` describes. Phase 6 fixes now go to `main`, each green in CI first.
- 2026-11-26: Prod Postgres is 18.7 (Railway template). Backup image and CI moved to Postgres 18 to match (`postgres:18.7-bookworm` pinned in the backup Dockerfile, CI, the restore drill and local docker-compose; restore-drill client tools `postgresql-client-18`).
- 2026-11-26 — **v2 (Premium launch) planned:** `CONTEXT_v2` added as section V2; v1 passages it supersedes are marked (tiers, "no accounts", hidden Sign in). v2 mockups in `design/v2/` (Pricing, SignIn, Account, StationPremium, Map). Q34 checked against raw METARs: real temperature rise, no bug. Phase 7 (accounts) on branch `v2-phase-7-accounts`, waiting for the owner's "go".
- 2026-11-26 — **Phase 7 (accounts) built** on `v2-phase-7-accounts` (owner "go" with additions: no enumeration on sign-up, fixed header placeholder, trusted origins incl. localhost/Railway/apex/www, trial button → /pricing, no staging, restricted role skipped if impractical). Done: Alembic 0007 `auth` schema; Better Auth (Google + email/password) with the rules in V2.9; Resend emails (verify, reset 1 h, password changed, account deleted, existing account) with console/file fallback locally; pages /signin, /check-email, /verify-email, /reset-password, /account; header states; FastAPI `X-Internal-Token` on `/api/v1/internal/*`; docs `infra/auth-setup.md`, `docs/privacy-data-inventory.md`. Tests: Vitest 94 (+ auth units), Playwright 64 (auth 13 flows × 1440/375 with a fake Google and an email outbox file), Lighthouse /signin and /account: a11y 100, best practices 100, CLS 0. CI: new `auth` job on Postgres 18.7 (deploy_db, Better Auth schema drift check, auth e2e on Postgres, secret value not in bundle). Nothing deployed.
- 2026-11-27 — Phase 7 closed: A1 fixes (status strip one line, mobile header menu, flaky = fail, auth e2e race) merged; production smoke test passed (owner: email sign-up/verify/sign-in, reset, Google, sign-out); CSP report-only warning fixed (PR #3).
- 2026-11-27 — **Phase 8 (billing, Stripe test mode)** in progress on `v2-phase-8-billing`: migration 0008, webhook mirror, entitlement, checkout/portal, account and pricing states, fake-Stripe e2e (see V2.10). Waiting for the owner's Stripe test key for the manual test-clock run.
- 2026-11-27 — **Phase 8 merged and live** (PR #4, production in Stripe **test** mode with `BILLING_TEST_ALLOWLIST`). Owner smoke test passed (4242 checkout → PREMIUM + trial; non-listed account sees "Premium is coming soon"). Verified from Stripe: production webhook endpoint enabled (7 events, API `2026-11-18.endive`), the test subscription `trialing` with Managed Payments, all its webhooks delivered (`pending_webhooks: 0`). Managed Payments ON (Link merchant of record, statement `LINK.COM* EDGEFRONT`), prices tax-exclusive ($20 + tax), tax code `txcd_10000000`.
- 2026-11-27 — **Phase 9 (5-minute HFMETAR)** started on `v2-phase-9-hfmetar`: LDM/Caddy guide (`infra/ldm/`), rights check (MADIS: "1-minute ASOS", category 3 public, no restrictions), Resend DNS update (CNAME `send`/`rsend`, DMARC → quarantine ~2026-12-11).
- 2026-11-28 — **Phase 10 (Premium UI + live map) built** on `v2-phase-10-premium-ui`: entitled routes `/api/premium/stations/{id}/hf`, `/hf-current`, `/api/premium/map` (session + billing-mirror entitlement on the server, per-user limit 120/min in `rateLimit`, `X-Internal-Token`, `private, no-store`, 403 with no data otherwise); public pages render the free version for everyone and Premium values load in the browser afterwards (leak tests on HTML + RSC); station page 5-MIN cards with the B9 lines, METAR comparison, stale/no-feed/QC/error states; observed chart 5-minute | Hourly METAR (gaps > 10 min empty); model overlay 5-minute; board 5-MIN values; `/map` with MapLibre 6.18.0 + OpenFreeMap and an automatic bundled-outline backup, button markers (spread when close, count clusters when zoomed out), list alternative, panel with Esc; shared 60 s polling (visible tab only, backoff 2 → 5 min); past_due banner → Customer Portal, "Premium until" note, activation every 3 s for 60 s; CSP adds OpenFreeMap + `worker-src`. Per-station 5-minute "stale" stays at 30 min (owner asked 15; upstream delay 13–18 min, see Phase 9 findings). E2E data: `python -m edgefront_core.e2e_seed` (refused in prod).
- 2026-11-28 — **Phase 9 accepted and closed** (owner): PR #5 merged (`31fe675`), `HF_INGEST_ENABLED=true` in production since 06:27Z, 26 stations reporting, rounding check 13/13, no errors. The 48 h continuous-data check moves to Phase 11. **Phase 10 (Premium UI + map)** started on `v2-phase-10-premium-ui`.
- 2026-11-28 — **Phase 9 B4–B8 built** on `v2-phase-9-hfmetar`: migration 0010 (`hf_observations`, `hf_files`), retention 7 days, worker job `hfmetar` behind `HF_INGEST_ENABLED` (off by default), 5-minute high/low so far with QC exclusions, internal endpoints `/hf`, `/hf-current`, `/map`, `/status` `hfmetar` block incl. the ongoing rounding check. Tests use the real cropped fixtures, including the real rewrite (3 new rows, QC-only changes, 0 value revisions). One full real file: ~0.3 s and ~57 MB peak to parse. **Live delay** (2026-11-28, real LDM API): observation → LDM file P50 12 min / P95 17 min (MADIS receives in ~2.3 min; the rest is upstream file production), so per-station "stale" is 30 min (`HF_STATION_STALE_MINUTES`); the 15-min alert is for no new readings at all.
- 2026-11-27 — **Phase 9 B6/B9 (done before the real 5-minute file):** METAR `low_so_far` (6-hour minimum groups inside the day) on the board and `/current`; structured temperatures `{c, f_exact, f_rounded, f_possible, precision, source, observed_at}`; rounding changed to the **NWS rule** (FMH-1 §2.6.3, floor(x+0.5), integer maths) from "half away from zero" (differs only for negative °F at exactly .5, i.e. below −17.8 °C); shared vectors `packages/core/tests/fixtures/temp_cases.json` run by Python and TypeScript. **Q36:** 27 of 28 stations measure in whole °F (every T-group value within ±0.09 °F of a whole °F, 3,031 reports; 18 % expected by chance); KBKF measures in °C → `stations.native_temp_unit` (migration 0009) + weekly drift check (worker, Mondays 10:00 UTC). ASOS °F→tenths °C is nearest (3,031/3,031); METAR body whole °C = NWS half-up of the T-group (3,121/3,125; the 4 exceptions are KSDF reports with the `$` maintenance flag). Free UI: station cards (current, high, new low) with "62.96 °F unrounded · 17.2 °C" (whole °C: "· reading 62–63 °F"); board High/Low so far "at 2:53 PM · 62.96°"; /sources paragraph.
