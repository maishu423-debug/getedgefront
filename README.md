# EdgeFront

Observed weather at the U.S. stations weather markets settle on. **Read [CONTEXT.md](CONTEXT.md) first.**

## Prerequisites

- Python 3.12 via [uv](https://docs.astral.sh/uv/)
- Node 24 LTS + pnpm 10 (`npm i -g pnpm@10`)
- Docker (optional, for the full stack)

## Setup

```sh
cp .env.example .env
uv sync
pnpm install
```

## Checks

```sh
# Python: lint, format, types, tests (SQLite unless TEST_DATABASE_URL points at Postgres)
uv run ruff check . && uv run ruff format --check .
uv run mypy packages/core/src services/api/src services/worker/src conftest.py
uv run pytest

# Web: lint, types, format, unit tests, build
pnpm --filter @edgefront/web check
pnpm --filter @edgefront/web build
```

## Run

Full stack with Docker:

```sh
docker compose --env-file .env -f infra/docker-compose.yml up --build
# web http://localhost:3000 · api http://localhost:8000/api/v1/health
```

Without Docker (any SQLAlchemy URL; SQLite works for the Phase 0 skeleton):

```sh
export DATABASE_URL=sqlite:///./local.db
uv run python -m edgefront_core.migrate
uv run python -m edgefront_core.seed             # load data/stations.yaml (idempotent)
uv run python -m edgefront_core.enrich_stations  # live upstream; needs CONTACT_EMAIL in .env
uv run uvicorn edgefront_api.main:build --factory --port 8000
uv run python -m edgefront_worker.main
cd apps/web && pnpm build && API_INTERNAL_URL=http://127.0.0.1:8000 pnpm start
```
