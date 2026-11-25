# Build context: repository root.  docker build -f services/api/Dockerfile .
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

# Dependencies first (cached layer), then source.
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/worker/pyproject.toml services/worker/pyproject.toml
RUN uv sync --frozen --no-dev --package edgefront-api --no-install-workspace

COPY packages/core packages/core
COPY data data
COPY services/api services/api
RUN uv sync --frozen --no-dev --package edgefront-api

RUN useradd --system --uid 10001 app
USER app

ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/api/v1/health', timeout=4)"

# Listens on [::]:$PORT and accepts IPv4 too (dual stack; see edgefront_api/serve.py).
CMD ["python", "-m", "edgefront_api.serve"]
