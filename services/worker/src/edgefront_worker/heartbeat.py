"""Worker heartbeat: proves the scheduler is alive and records it in source_health('worker')."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.source_health import record_failure, record_success
from edgefront_core.timeutil import utcnow

log = logging.getLogger("edgefront.worker.heartbeat")

SOURCE = "worker"


def heartbeat(factory: sessionmaker[Session], now: Callable[[], datetime] = utcnow) -> bool:
    """Write one heartbeat. Return True on success; never raise (the scheduler must keep going)."""
    started = time.perf_counter()
    at = now()
    try:
        with session_scope(factory) as s:
            record_success(s, SOURCE, at)
    except (SQLAlchemyError, OSError) as exc:
        log.error(
            "heartbeat failed",
            extra={"source": SOURCE, "error": f"{type(exc).__name__}: {exc}"[:500]},
        )
        try:
            with session_scope(factory) as s:
                record_failure(s, SOURCE, at, type(exc).__name__)
        except (SQLAlchemyError, OSError):
            pass  # DB is down; the log line above is the record.
        return False
    log.info(
        "heartbeat",
        extra={
            "source": SOURCE,
            "at": at.isoformat(),
            "duration_ms": round((time.perf_counter() - started) * 1000),
        },
    )
    return True
