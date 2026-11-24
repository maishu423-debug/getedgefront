"""Health check logic (kept out of the route handler)."""

from __future__ import annotations

import logging

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from edgefront_api.schemas import HealthResponse
from edgefront_core.db import ping
from edgefront_core.timeutil import utcnow

log = logging.getLogger(__name__)


def check_health(engine: Engine) -> HealthResponse:
    try:
        ping(engine)
        db_ok = True
    except (SQLAlchemyError, OSError) as exc:
        log.warning("db ping failed", extra={"error": type(exc).__name__})
        db_ok = False
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db="ok" if db_ok else "unreachable",
        generated_at=utcnow(),
    )
