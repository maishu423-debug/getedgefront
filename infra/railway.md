# Railway: build the production project from scratch

Written so the owner can recreate everything by following it top to bottom. Facts about Railway
were checked against docs.railway.com on 2026-11-26 (links inline).

> **Why click-by-click, not a config file:** Railway's `railway.json` ("Config as Code") is
> deprecated, stops being read on **2026-12-01**, and new services cannot opt into it. Its
> replacement ("Infrastructure as Code", `.railway/railway.ts`) is applied with the Railway CLI
> (`railway config apply`). Until we decide to adopt that (optional, later), every setting lives
> in the dashboard and is listed here.

## 0. What you end up with

| Service | Source | Public? | Port | Notes |
|---|---|---|---|---|
| `web` | repo `main`, `apps/web/Dockerfile` | **yes, the only public service** | `PORT` (Railway sets it) | Next.js, listens on `::` |
| `api` | repo `main`, `services/api/Dockerfile` | no | `8000` | FastAPI; runs migrations + seed before each deploy |
| `worker` | repo `main`, `services/worker/Dockerfile` | no | none | exactly 1 replica; the only process that contacts upstream sources |
| `backup` | repo `main`, `services/backup/Dockerfile` | no | none | cron `30 7 * * *` (UTC), pg_dump → your S3 bucket, exits |
| `Postgres` | Railway Postgres template | no | 5432 (private) | volume attached; **no public TCP proxy** |

All services talk over Railway's private network (`<service>.railway.internal`, plain `http://`,
encrypted by Railway's WireGuard). New environments (created after 2025-10-16) resolve those names
to IPv4 **and** IPv6, so every service listens on `::` with IPv4 accepted
([private networking](https://docs.railway.com/networking/private-networking/how-it-works)).

## 1. Project and Postgres

1. railway.com → **New Project** → **Empty project**. Name it `edgefront`. Environment: keep
   `production` (a new project gets a new, dual-stack environment).
2. **+ Create → Database → PostgreSQL**. Rename the service to `Postgres` (the reference
   variables below use that name). Railway attaches a volume automatically.
3. Postgres service → **Settings → Networking**: make sure there is **no TCP Proxy / Public
   Networking** entry. If one exists, delete it (trash-can icon). Databases are private by default
   ([PostgreSQL guide](https://docs.railway.com/guides/postgresql)); a TCP proxy is what makes
   `DATABASE_PUBLIC_URL` work from the internet.
4. Note the Postgres major version shown in the service (CI tests against Postgres 17; the backup
   image ships pg_dump 17, which can dump 17 and older).

## 2. Connect the GitHub repo

**+ Create → GitHub Repo →** the private EdgeFront repo (authorize the Railway GitHub app for that
repo only). Repeat for each of `api`, `worker`, `web`, `backup` (four services from the same repo),
then rename each service exactly as in the table (the names become the private DNS names).

For **each** of these four services, **Settings → Source / Build**:

| Setting | api | worker | web | backup |
|---|---|---|---|---|
| Branch | `main` | `main` | `main` | `main` |
| Root directory | *(empty: repo root, the Dockerfiles copy from several folders)* | same | same | same |
| Builder | Dockerfile | Dockerfile | Dockerfile | Dockerfile |
| Dockerfile path | `services/api/Dockerfile` | `services/worker/Dockerfile` | `apps/web/Dockerfile` | `services/backup/Dockerfile` |
| Watch paths | `services/api/**` `packages/core/**` `data/**` `pyproject.toml` `uv.lock` | `services/worker/**` `packages/core/**` `data/**` `pyproject.toml` `uv.lock` | `apps/web/**` `data/stations.yaml` `package.json` `pnpm-lock.yaml` `pnpm-workspace.yaml` | `services/backup/**` |

Base images are pinned in the Dockerfiles: `python:3.12.16-slim-bookworm`, `node:24.22.2-bookworm-slim`,
`postgres:17.12-bookworm` (Debian 12 "bookworm" everywhere), `ghcr.io/astral-sh/uv:0.13.7`.

## 3. Deploy settings per service

**api** → Settings → Deploy
- **Pre-deploy command:** `python -m edgefront_core.deploy_db` (Alembic migrations to head, then the
  idempotent station seed; a failure stops the deploy and the old version keeps serving). If the
  logs show it cannot reach `postgres.railway.internal` (private networking exists only at
  runtime), move it into the start command instead: `sh -c "python -m edgefront_core.deploy_db && python -m edgefront_api.serve"`.
- Start command: leave empty (Dockerfile `CMD python -m edgefront_api.serve`, dual-stack on `::`).
- **Healthcheck path:** `/api/v1/health`, timeout `60` s.
- Restart policy: **On failure**, max retries `10`.
- **Networking:** no public domain, no TCP proxy.

**worker** → Settings → Deploy
- **Replicas: 1** (never more). A Postgres advisory lock also makes a second copy wait instead of
  running jobs twice; during a redeploy Railway overlaps old and new deployments briefly, and the
  new worker starts its jobs as soon as the old one has stopped
  ([deployments](https://docs.railway.com/reference/deployments)). Optional variable
  `RAILWAY_DEPLOYMENT_DRAINING_SECONDS=20` gives the old worker time to finish a write.
- Restart policy: **On failure**, max retries `10`. No healthcheck (no port), no domain.
- Memory limit (Settings → Resources): start at **1 GB** (measured peak ~160 MB; see B8 report).

**web** → Settings → Deploy
- Healthcheck path: `/`, timeout `60` s. Restart policy: **On failure**, max retries `10`.
- **Networking → Generate Domain** (a `*.up.railway.app` address). This is the production URL
  until "go live". Custom domain: section 6, only after the owner says "go live".

**backup** → Settings → Deploy
- **Cron schedule:** `30 7 * * *` (UTC; 07:30Z = 01:30–03:30 local in the US, after the night's
  CLI/DSM finals). Restart policy: **Never**. The job runs, exits, and Railway starts it again at the
  next schedule ([cron jobs](https://docs.railway.com/reference/cron-jobs)).
- No domain, no port.

## 4. Variables (Settings → Variables). Secrets marked 🔒

Railway stages variable changes; click **Deploy** to apply them
([variables](https://docs.railway.com/guides/variables)). `${{Postgres.DATABASE_URL}}` is a
reference variable: type it literally, do not paste the URL.

**api**

| Variable | Value | |
|---|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | 🔒 (reference) |
| `APP_ENV` | `prod` | |
| `LOG_LEVEL` | `INFO` | |
| `PORT` | `8000` | |
| `STALE_METAR_MINUTES` | `90` | |
| `METAR_POLL_SECONDS`, `CLI_POLL_SECONDS`, `DSM_POLL_SECONDS`, `FORECAST_POLL_SECONDS`, `MODEL_POLL_SECONDS` | `180`, `900`, `720`, `1800`, `900` | (`/status` health uses them) |

**worker**

| Variable | Value | |
|---|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | 🔒 (reference) |
| `CONTACT_EMAIL` | the owner's contact address | 🔒 set by the owner; never committed. Without it the worker refuses to start |
| `APP_ENV`, `LOG_LEVEL` | `prod`, `INFO` | |
| poll intervals | same five as api | |
| `STALE_METAR_MINUTES` | `90` | |
| `DB_SIZE_WARN_BYTES` | `3221225472` (3 GB) | |
| `WORKER_UPSTREAM_ENABLED` | `true` | |

**web**

| Variable | Value | |
|---|---|---|
| `API_INTERNAL_URL` | `http://api.railway.internal:8000` | |
| `NEXT_PUBLIC_SITE_URL` | `https://<generated>.up.railway.app` now; `https://getedgefront.com` after go-live (needs a redeploy: it is built in) | |
| `INDEXING_ENABLED` | `false` until go-live | |
| `CSP_MODE` | `report-only` for the first days, then `enforce` | |
| `HSTS_ENABLED` | `false` until the custom domain serves HTTPS | |
| `RATE_LIMIT_PER_MINUTE` | `120` | |
| `HOSTNAME` | `::` (also set in the Dockerfile) | |

**backup**

| Variable | Value | |
|---|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | 🔒 |
| `BACKUP_S3_ENDPOINT` | R2: `https://<account-id>.r2.cloudflarestorage.com`; B2: `https://s3.<region>.backblazeb2.com` | 🔒 |
| `BACKUP_S3_BUCKET` | your private bucket | 🔒 |
| `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY` | a key limited to that bucket | 🔒 |
| `BACKUP_S3_REGION` | `auto` (R2) or the B2 region | |
| `BACKUP_PREFIX` | `edgefront/` | |

Nothing secret is ever built into the browser bundle: CI runs `apps/web/scripts/check-bundle.mjs`
after the build (fails on secret names, DB URLs, `railway.internal` or e-mail addresses).

## 5. First deploy checklist

1. Deploy `Postgres`, then `api` (watch the pre-deploy log: "migrations applied", "registry seeded").
2. Deploy `worker`: the log shows `upstream identity` with `contact_set: true`, then `worker lock
   acquired`, then jobs.
3. Run station enrichment once (positions, NWS office/grid, PFM points): `worker` → **⋯ → Run
   command** (or Railway shell) `python -m edgefront_core.enrich_stations`.
4. Deploy `web`; open the generated domain. `/api/health` should say `"status":"ok"` within ~30 min
   (all sources must have run once).
5. Deploy `backup` once by hand (**Deploy → Run now**) and check the bucket for
   `edgefront/daily/edgefront-…dump`.

## 6. Custom domain (only after the owner says "go live")

On `web` → **Settings → Networking → Custom Domain**: add `getedgefront.com`, then add
`www.getedgefront.com`. Railway shows, per domain, a **CNAME** target (like `xxxxxx.up.railway.app`)
and a **TXT** verification record (name + value). **Both are required**; without the TXT the domain
answers 404 ([working with domains](https://docs.railway.com/networking/domains/working-with-domains)).

**A. Registrar supports CNAME flattening / ALIAS / ANAME at the apex** (e.g. Cloudflare, DNSimple,
Namecheap, bunny.net):
1. Apex: record `@` → type CNAME (or ALIAS/ANAME) → the target Railway shows for `getedgefront.com`.
2. `www`: CNAME → the target Railway shows for `www.getedgefront.com`.
3. Both TXT records exactly as shown.
4. Wait for Railway to show both domains verified and the certificate issued (minutes; DNS can take
   up to 72 h).

**B. Registrar cannot (Route 53, Azure DNS, GoDaddy, Hostinger and others): move DNS to Cloudflare.**
1. Cloudflare → Add site `getedgefront.com` (Free plan) → copy the two Cloudflare nameservers.
2. At the registrar, replace the nameservers with Cloudflare's. Wait until Cloudflare says active.
3. In Cloudflare DNS: `@` CNAME → Railway target, `www` CNAME → Railway's `www` target, the TXT
   records; set the CNAMEs to **DNS only (grey cloud)**. (If you later turn the orange-cloud proxy
   on, Cloudflare's SSL mode must be **Full**, not Full (strict), or you get redirect loops.)
4. **www → apex 301:** Railway serves both names; the redirect is done in Cloudflare: Rules →
   **Bulk Redirects**: `https://www.getedgefront.com` → `https://getedgefront.com`, status **301**,
   preserve path + query. (With option A and no Cloudflare, add the same redirect at your DNS host
   if it offers one; otherwise keep `www` as a second name and the site's canonical URLs point to
   the apex.)

**After the domain works** (in this order): set `NEXT_PUBLIC_SITE_URL=https://getedgefront.com`
and redeploy `web` (canonicals, sitemap, OpenGraph use it); set `HSTS_ENABLED=true`; check
`/robots.txt`, `/sitemap.xml` and a page's `<link rel="canonical">`; then — on the owner's word —
`INDEXING_ENABLED=true` (removes `X-Robots-Tag: noindex` and opens robots.txt).

## 7. Exposure checks (run after every infrastructure change)

```sh
curl -sI https://<web-domain>/ | grep -iE "x-robots-tag|content-security|x-content-type|referrer|x-frame"
curl -s  https://<web-domain>/api/health
# The API and Postgres must NOT be reachable from the internet:
curl -s --max-time 10 http://api.railway.internal:8000/api/v1/health   # must fail (no such host outside Railway)
# and Railway must show no domain / TCP proxy on api, worker, backup, Postgres
```

## 8. Uptime monitoring (owner creates the account; free tier)

UptimeRobot (free: 50 monitors, 5-minute checks, e-mail alerts) or Better Stack (free tier) both
work. Steps for UptimeRobot:
1. uptimerobot.com → sign up with the owner's e-mail → **Alert contacts**: confirm that e-mail.
2. **New monitor → HTTP(s)** — name `EdgeFront web`, URL `https://<web-domain>/`, interval 5 min.
   Alerts on any non-2xx/3xx or timeout.
3. **New monitor → Keyword** — name `EdgeFront data`, URL `https://<web-domain>/api/health`, keyword
   `"status":"ok"`, alert when the keyword is **missing**. `/api/health` answers
   `{"status":"ok"}` when the API, its database and every ingest source (METAR, CLI, DSM ×2,
   forecast, 7 models, worker heartbeat, retention) are healthy; `"degraded"` plus
   `unhealthy_sources: [...]` when a source is late; HTTP 503 `"down"` when the API or DB is down.
4. Send a **test notification** from the monitor's menu and confirm the e-mail arrives (launch
   checklist item). After go-live, change both URLs to `https://getedgefront.com`.

Logs: every service writes one JSON object per line (`ts`, `level`, `logger`, `msg`, `source`,
counts, durations, errors), so Railway's log view can filter, e.g. `@level:ERROR` or
`@source:model_gfs`. The worker logs one line per job run; the nightly `retention` line carries
row counts per table and `db_mb`, and becomes a `WARNING` above `DB_SIZE_WARN_BYTES` (3 GB).

## Before launch: third-party data sources

### Iowa Environmental Mesonet (IEM): DSM source for 24 stations

- **Owner action: email IEM (Daryl Herzmann, akrherz@iastate.edu) about our use** before going live:
  what we fetch (DSM text products via `/api/1/nws/afos/list.json` and `/api/1/nwstext/{product_id}`),
  how often (one list request per station every ~12 min with jitter, product text only for new
  products), and the User-Agent we send: the same as for NWS, `EdgeFront/1.0 (getedgefront.com;
  <CONTACT_EMAIL>)`, so IEM can see who we are and reach us.
- Terms (owner review, Q17): data described as public domain, usable "for any lawful purpose", no
  warranty, attribution appreciated. **We attribute** on the station page and `/sources`: "DSM via
  Iowa Environmental Mesonet, Iowa State University".
- Optional future upgrade: **NWWS-OI** as another DSM/CLI fetcher.

### NWS / NOAA / ECMWF

- `CONTACT_EMAIL` must be set on `worker` (NWS User-Agent requirement). It is never committed.
- ECMWF open data (IFS, AIFS): CC BY 4.0; attribution is on the station pages, `/sources` and the
  footer.
