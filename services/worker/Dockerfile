# Build context: repository root.  docker build -f services/worker/Dockerfile .
# Debian-based on purpose: Phase 5 adds GRIB decoding, which needs eccodes from apt:
#   RUN apt-get update && apt-get install -y --no-install-recommends libeccodes-dev && rm -rf /var/lib/apt/lists/*
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/worker/pyproject.toml services/worker/pyproject.toml
RUN uv sync --frozen --no-dev --package edgefront-worker --no-install-workspace

COPY packages/core packages/core
COPY data data
COPY services/worker services/worker
RUN uv sync --frozen --no-dev --package edgefront-worker

RUN useradd --system --uid 10001 app
USER app

CMD ["python", "-m", "edgefront_worker.main"]
