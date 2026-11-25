"""FastAPI app (read-only; Postgres only). Run: `uvicorn edgefront_api.main:build --factory`."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Iterator
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Query, Request, Response
from fastapi import status as http
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from starlette.responses import Response as StarletteResponse

from edgefront_api import daily, model_guidance, services
from edgefront_api import schemas as s
from edgefront_api.health import check_health
from edgefront_core.db import get_engine, make_sessionmaker
from edgefront_core.logs import configure_logging
from edgefront_core.models import Station
from edgefront_core.settings import Settings, get_settings
from edgefront_core.timeutil import utcnow

API_PREFIX = "/api/v1"
CACHE_SECONDS = 30

router = APIRouter(prefix=API_PREFIX)


# ---------------------------------------------------------------- dependencies


def get_session(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.sessionmaker()
    try:
        yield session
    finally:
        session.close()


def get_now(request: Request) -> datetime:
    now: Callable[[], datetime] = request.app.state.now
    return now()


def get_cfg(request: Request) -> Settings:
    cfg: Settings = request.app.state.settings
    return cfg


SessionDep = Annotated[Session, Depends(get_session)]
NowDep = Annotated[datetime, Depends(get_now)]
CfgDep = Annotated[Settings, Depends(get_cfg)]
StationId = Annotated[str, Path(pattern=r"^[A-Za-z][A-Za-z0-9]{3}$")]


def station_or_404(session: SessionDep, station_id: StationId) -> Station:
    try:
        return services.get_station(session, station_id)
    except services.NotFoundError:
        raise HTTPException(http.HTTP_404_NOT_FOUND, f"Unknown station {station_id}") from None


StationDep = Annotated[Station, Depends(station_or_404)]


# ---------------------------------------------------------------- routes


@router.get(
    "/health",
    response_model=s.HealthResponse,
    responses={503: {"model": s.HealthResponse, "description": "Database unreachable"}},
)
def health(request: Request, response: Response) -> s.HealthResponse:
    engine: Engine = request.app.state.engine
    result = check_health(engine)
    response.headers["Cache-Control"] = "no-store"
    if result.status != "ok":
        response.status_code = http.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get("/status", response_model=s.StatusResponse)
def status(session: SessionDep, now: NowDep, cfg: CfgDep) -> s.StatusResponse:
    return services.status(session, now, cfg)


@router.get("/stations", response_model=s.StationsResponse)
def stations(
    session: SessionDep,
    now: NowDep,
    cfg: CfgDep,
    venue: Annotated[Literal["kalshi", "polymarket", "robinhood"] | None, Query()] = None,
) -> s.StationsResponse:
    return services.board(session, now, cfg, venue)


@router.get("/stations/{station_id}", response_model=s.StationResponse)
def station(session: SessionDep, st: StationDep, now: NowDep) -> s.StationResponse:
    return s.StationResponse(
        generated_at=now,
        station=services.station_meta(session, st, now),
        climate_day=services.climate_day_out(st, now),
    )


@router.get("/stations/{station_id}/current", response_model=s.CurrentResponse)
def current(session: SessionDep, st: StationDep, now: NowDep, cfg: CfgDep) -> s.CurrentResponse:
    return services.current(session, st, now, cfg)


@router.get("/stations/{station_id}/metars", response_model=s.MetarsResponse)
def metars(
    session: SessionDep,
    st: StationDep,
    now: NowDep,
    cfg: CfgDep,
    hours: Annotated[int, Query(ge=1, le=48)] = 24,
) -> s.MetarsResponse:
    return services.metars(session, st, now, cfg, hours)


@router.get("/stations/{station_id}/observed", response_model=s.ObservedResponse)
def observed(
    session: SessionDep,
    st: StationDep,
    now: NowDep,
    cfg: CfgDep,
    hours: Annotated[int, Query(description="6 or 24")] = 24,
) -> s.ObservedResponse:
    if hours not in (6, 24):
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_CONTENT, "hours must be 6 or 24")
    return services.observed(session, st, now, cfg, hours)


@router.get("/stations/{station_id}/daily-summaries", response_model=s.DailySummariesResponse)
def daily_summaries(st: StationDep, session: SessionDep, now: NowDep) -> s.DailySummariesResponse:
    return daily.daily_summaries(session, st, now)


@router.get("/stations/{station_id}/forecast", response_model=s.ForecastResponse)
def forecast(st: StationDep, session: SessionDep, now: NowDep, cfg: CfgDep) -> s.ForecastResponse:
    return daily.forecast(session, st, now, cfg)


@router.get("/stations/{station_id}/models", response_model=s.ModelsResponse)
def models(
    st: StationDep,
    session: SessionDep,
    now: NowDep,
    var: Annotated[s.ModelVariable, Query(description="temp | dewpt | wind | cloud | rh")] = "temp",
    span: Annotated[Literal["today", "48h"], Query(description="today | 48h")] = "today",
) -> s.ModelsResponse:
    return model_guidance.models(session, st, now, var, span)


@router.get("/feed/new-highs", response_model=s.FeedResponse)
def new_highs(
    session: SessionDep,
    now: NowDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> s.FeedResponse:
    return services.new_highs(session, now, limit)


# ---------------------------------------------------------------- caching


def etag_for(body: bytes) -> str:
    """ETag over the data, ignoring the top-level `generated_at` (it changes on every request,
    which would make every ETag unique)."""
    try:
        doc = json.loads(body)
    except ValueError:
        digest = hashlib.sha256(body).hexdigest()
    else:
        if isinstance(doc, dict):
            doc.pop("generated_at", None)
        digest = hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()
    return f'"{digest[:32]}"'


async def cache_headers(
    request: Request, call_next: Callable[[Request], Awaitable[StarletteResponse]]
) -> StarletteResponse:
    """Cache-Control: max-age=30 + strong ETag on successful read endpoints (§8)."""
    response = await call_next(request)
    path = request.url.path
    if (
        request.method != "GET"
        or response.status_code != 200
        or not path.startswith(API_PREFIX)
        or path == f"{API_PREFIX}/health"
        or response.headers.get("content-type", "").split(";")[0] != "application/json"
    ):
        return response
    body = b"".join([chunk async for chunk in response.body_iterator])  # type: ignore[attr-defined]
    etag = etag_for(body)
    headers = dict(response.headers)
    headers.pop("content-length", None)
    headers["ETag"] = etag
    headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"
    if request.headers.get("if-none-match") == etag:
        return StarletteResponse(
            status_code=304, headers={"ETag": etag, "Cache-Control": headers["Cache-Control"]}
        )
    return StarletteResponse(
        content=body, status_code=200, headers=headers, media_type="application/json"
    )


# ---------------------------------------------------------------- app


def create_app(
    engine: Engine | None = None,
    *,
    now: Callable[[], datetime] = utcnow,
    settings: Settings | None = None,
) -> FastAPI:
    cfg = settings or get_settings()
    dev = cfg.app_env == "dev"
    app = FastAPI(
        title="EdgeFront API",
        version="0.2.0",
        docs_url=f"{API_PREFIX}/docs" if dev else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if dev else None,
    )
    app.state.engine = engine if engine is not None else get_engine()
    app.state.sessionmaker = make_sessionmaker(app.state.engine)
    app.state.now = now
    app.state.settings = cfg
    app.middleware("http")(cache_headers)
    app.include_router(router)
    return app


def build() -> FastAPI:
    """Production entry point (uvicorn --factory)."""
    configure_logging(get_settings().log_level)
    return create_app()
