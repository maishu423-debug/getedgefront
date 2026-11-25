# Build context: repository root.  docker build -f services/worker/Dockerfile .
# GRIB decoding (Phase 5) uses the `eccodes` Python package; on Linux its native library comes
# from the `eccodeslib` manylinux wheel (uv.lock), so no apt package is needed. The worker imports
# eccodes at start-up, so a broken install fails the CI stack's heartbeat check.
# Pinned: Python 3.12.16 on Debian 12 (bookworm).
FROM python:3.12.16-slim-bookworm

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
