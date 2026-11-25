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

**None are needed for CI today.** The Python job uses a throw-away Postgres service container
(`edgefront/edgefront`, database `edgefront_test`) and never contacts upstream sources; tests use
saved fixtures. `CONTACT_EMAIL` is only needed by the worker in deployed environments (Railway),
not in CI.

If a later phase needs one, add it under *Settings → Secrets and variables → Actions* and list it
here.

## 3. Branch protection (recommended)

*Settings → Branches → Add rule* for `main`:
- Require a pull request before merging.
- Require status checks to pass: `python`, `web`, `docker`.

## What the CI jobs do

| Job | Steps |
|---|---|
| `python` | uv sync → ruff → mypy → **migrate up → down to base → up on Postgres 16** → full pytest suite on Postgres (`REQUIRE_POSTGRES=1` fails the run if it silently falls back to SQLite) |
| `web` | pnpm install → lint → typecheck → prettier → Vitest → `next build` (the build never calls the API) |
| `docker` | build all images, bring the stack up, check API health, the homepage and a worker heartbeat |

## Where Postgres is tested (owner rule, 2026-11-25)

**There is no Docker and no Postgres on the development machine, and none will be installed.**
Local development and the local test run use SQLite (`uv run pytest`; the 12 Postgres-only tests
are skipped locally). Postgres is verified **only** by the `python` job in GitHub Actions, which
runs the whole suite plus migrate up → down → up against a Postgres 16 service container with
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
