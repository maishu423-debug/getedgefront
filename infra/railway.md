# Railway deploy notes

> Phase 6 fills in the full deploy guide (services, build settings, env vars, private networking, health checks, custom domain). This file collects notes that must not be forgotten before launch.

## Before launch: third-party data sources

### Iowa Environmental Mesonet (IEM) — DSM source for 24 stations

- **Owner action: email IEM (Daryl Herzmann, akrherz@iastate.edu) about our use** before going live: what we fetch (DSM text products via `/api/1/nws/afos/list.json` and `/api/1/nwstext/{product_id}`), how often (one list request per station every ~12 min with jitter, product text only for new products), and the User-Agent we send (`EdgeFront/1.0 (getedgefront.com)`). IEM is a university service; its CGI endpoints are heavily used.
- Terms (owner review, Q17): data described as public domain, usable "for any lawful purpose", no warranty, attribution appreciated. **We attribute** on the station page and `/sources`: "DSM via Iowa Environmental Mesonet, Iowa State University".
- IEM is only contacted by the worker, never from a page request. If IEM is down, the site keeps serving the latest stored DSM with its issue time and age, and the `dsm_iem` source shows unhealthy on the status strip.
- Optional future upgrade: **NWWS-OI** (NOAA Weather Wire Service – Open Interface; free, sign-up required) as another DSM/CLI fetcher (`edgefront_core.dsm_ingest.DsmFetcher`).

### NWS / NOAA

- `CONTACT_EMAIL` must be set in the worker's environment (NWS User-Agent requirement). It is never committed.
