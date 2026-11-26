# GitHub setup (owner steps)

CI (`.github/workflows/ci.yml`) runs on every push to `main` and `phase-*` branches and on pull
requests. **Rule (owner, Phase 5 A2): no phase is "done" until the Postgres CI job is green.**

## 1. Create the repository (owner)

1. Create a **private** repository on GitHub (e.g. `getedgefront/edgefront`). Do not add a README,
   licence or .gitignore (the local repo already has history).
2. Give Claude the remote URL (HTTPS or SSH).
3. Make sure the machine that pushes can authenticate (GitHub CLI `gh auth login`, a credential
   manager, or an SSH key). Never paste tokens into chat or commit them.

Claude then runs:

```sh
git remote add origin <URL>
git push -u origin main
git push origin phase-4-frontend phase-5-models   # and any other open phase branches
```

## 2. Secrets

**None are needed for the CI workflow.** The Python job uses a throw-away Postgres service container
(`edgefront/edgefront`, database `edgefront_test`) and never contacts upstream sources; tests use
saved fixtures. `CONTACT_EMAIL` is only needed by the worker in deployed environments (Railway),
not in CI.

Only the manual **Restore drill** workflow uses secrets (*Settings → Secrets and variables →
Actions → New repository secret*): `BACKUP_S3_ENDPOINT`, `BACKUP_S3_BUCKET`,
`BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY`, `BACKUP_S3_REGION` (a read-only key for
the backup bucket is enough). See `infra/backup-restore.md`.

Railway deploys from `main` through the Railway GitHub app (installed on this repository only); no
deploy token is stored in GitHub.

## 3. Branch protection (recommended)

*Settings → Branches → Add rule* for `main`:
- Require a pull request before merging.
- Require status checks to pass: `python`, `web`, `audit`, `docker`.
- Require branches to be up to date before merging; do not allow force pushes to `main`.

## What the CI jobs do

| Job | Steps |
|---|---|
| `python` | uv sync → ruff → mypy → **migrate up → down to base → up on Postgres 18** → full pytest suite on Postgres (`REQUIRE_POSTGRES=1` fails the run if it silently falls back to SQLite) |
| `web` | pnpm install → lint → typecheck → prettier → Vitest → `next build` (the build never calls the API) |
| `web` (added Phase 6) | … then `check-bundle.mjs`: no secret names, DB URLs or e-mail addresses in the browser bundle |
| `audit` | `pnpm audit --prod` and `pip-audit` on the locked production Python dependencies |
| `docker` | build all images (incl. `backup`), bring the stack up with `WORKER_UPSTREAM_ENABLED=false` (CI never contacts NOAA/NWS/IEM/ECMWF), check API health, the homepage, `/api/health`, `X-Robots-Tag: noindex`, and a worker heartbeat |
| `Restore drill` (manual) | restore the newest bucket backup (or a synthetic one) into a throwaway Postgres 18 and check it |

## Where Postgres is tested (owner rule, 2026-11-25)

**There is no Docker and no Postgres on the development machine, and none will be installed.**
Local development and the local test run use SQLite (`uv run pytest`; the 12 Postgres-only tests
are skipped locally). Postgres is verified **only** by the `python` job in GitHub Actions, which
runs the whole suite plus migrate up → down → up against a Postgres 18 (`postgres:18.7-bookworm`) service container with
`REQUIRE_POSTGRES=1`. **A phase is done only when that job is green.**

## (Reference only) Running the Python tests against Postgres with Docker

One line, from the repo root:

```sh
docker compose -f infra/docker-compose.yml up -d --wait postgres && TEST_DATABASE_URL=postgresql+psycopg://edgefront:edgefront@localhost:5432/edgefront_test REQUIRE_POSTGRES=1 uv run pytest
```

(PowerShell: `docker compose -f infra/docker-compose.yml up -d --wait postgres; $env:TEST_DATABASE_URL="postgresql+psycopg://edgefront:edgefront@localhost:5432/edgefront_test"; $env:REQUIRE_POSTGRES="1"; uv run pytest`)

The test fixture drops and recreates the `public` schema of that database for every test. It uses
`edgefront_test`, created by `infra/postgres-init/01-test-db.sql` (if your `pgdata` volume existed before
that script, run `docker compose -f infra/docker-compose.yml down -v` once). Never point it at a
database with data you want to keep.
