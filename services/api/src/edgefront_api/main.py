"""FastAPI app. Run: `uvicorn edgefront_api.main:app`."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request, Response, status
from sqlalchemy import Engine

from edgefront_api.health import check_health
from edgefront_api.schemas import HealthResponse
from edgefront_core.db import get_engine
from edgefront_core.logs import configure_logging
from edgefront_core.settings import get_settings

API_PREFIX = "/api/v1"

router = APIRouter(prefix=API_PREFIX)


def _engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Database unreachable"}},
)
def health(request: Request, response: Response) -> HealthResponse:
    result = check_health(_engine(request))
    response.headers["Cache-Control"] = "no-store"
    if result.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


def create_app(engine: Engine | None = None) -> FastAPI:
    settings = get_settings()
    dev = settings.app_env == "dev"
    app = FastAPI(
        title="EdgeFront API",
        version="0.1.0",
        docs_url=f"{API_PREFIX}/docs" if dev else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if dev else None,
    )
    app.state.engine = engine if engine is not None else get_engine()
    app.include_router(router)
    return app


def build() -> FastAPI:
    """Production entry point (uvicorn --factory)."""
    configure_logging(get_settings().log_level)
    return create_app()
