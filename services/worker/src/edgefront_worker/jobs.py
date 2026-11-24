"""Scheduled ingest jobs. Each job is idempotent and never raises into the scheduler."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.http import make_client
from edgefront_core.metar_ingest import run_metar_ingest

log = logging.getLogger("edgefront.worker.jobs")


def metar_job(factory: sessionmaker[Session]) -> None:
    try:
        with make_client() as client:
            run_metar_ingest(factory, client)
    except Exception:  # already logged + recorded in source_health by run_metar_ingest
        log.warning("metar job ended with an error", extra={"source": "metar"})
