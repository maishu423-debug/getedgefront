"""Worker entry point: `python -m edgefront_worker.main`."""

from __future__ import annotations

import logging
import signal
from datetime import timedelta
from types import FrameType

from apscheduler.schedulers.blocking import BlockingScheduler

from edgefront_core.db import get_engine, make_sessionmaker
from edgefront_core.logs import configure_logging
from edgefront_core.settings import get_settings
from edgefront_core.timeutil import utcnow
from edgefront_worker.heartbeat import heartbeat
from edgefront_worker.jobs import ProductJobs, metar_job, native_unit_job, retention_job
from edgefront_worker.lock import hold_worker_lock

log = logging.getLogger("edgefront.worker")


def build_scheduler() -> BlockingScheduler:
    settings = get_settings()
    factory = make_sessionmaker(get_engine())
    scheduler = BlockingScheduler(
        timezone="UTC",
        # Per-job lock: never run two instances of the same job; collapse missed runs.
        job_defaults={"max_instances": 1, "coalesce": True, "misfire_grace_time": 30},
    )
    scheduler.add_job(
        heartbeat,
        "interval",
        seconds=settings.heartbeat_seconds,
        args=[factory],
        id="heartbeat",
        next_run_time=utcnow(),
    )
    scheduler.add_job(
        retention_job,
        "cron",
        hour=9,
        minute=30,  # 09:30 UTC: after the overnight CLI/DSM finals, before US daytime
        args=[factory],
        id="retention",
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        native_unit_job,  # stored METARs only: no upstream traffic
        "cron",
        day_of_week="mon",
        hour=10,
        minute=0,
        args=[factory],
        id="native_unit_check",
        misfire_grace_time=6 * 3600,
    )
    if not settings.worker_upstream_enabled:
        log.warning("upstream jobs disabled (WORKER_UPSTREAM_ENABLED=false): heartbeat only")
        return scheduler
    scheduler.add_job(
        metar_job,
        "interval",
        seconds=settings.metar_poll_seconds,
        jitter=20,
        args=[factory],
        id="metar",
        next_run_time=utcnow(),  # first run backfills 36 h
        misfire_grace_time=120,
    )
    products = ProductJobs()
    start = utcnow()
    for job_id, fn, seconds, jitter, delay in [
        ("cli", products.cli, settings.cli_poll_seconds, 60, 20),
        ("dsm", products.dsm, settings.dsm_poll_seconds, 90, 40),
        ("forecast", products.forecast, settings.forecast_poll_seconds, 120, 60),
        ("models_text", products.models_text, settings.model_poll_seconds, 120, 80),
        ("models_grib", products.models_grib, settings.model_poll_seconds, 120, 140),
    ]:
        scheduler.add_job(
            fn,
            "interval",
            seconds=seconds,
            jitter=jitter,
            args=[factory],
            id=job_id,
            next_run_time=start + timedelta(seconds=delay),  # stagger the first runs
            misfire_grace_time=300,
        )
    return scheduler


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.worker_upstream_enabled and not settings.contact_email:
        log.error("CONTACT_EMAIL is not set: refusing to contact NWS/NOAA/IEM/ECMWF without it")
        raise SystemExit(2)
    log.info(
        "upstream identity",
        extra={
            "user_agent_product": settings.user_agent.split(" (", 1)[0],
            "contact_set": bool(settings.contact_email),
            "upstream_enabled": settings.worker_upstream_enabled,
        },
    )
    # Exactly one worker may run jobs (APScheduler in two copies would run everything twice).
    # A second copy waits here until the first one exits, e.g. during a Railway redeploy.
    lock = hold_worker_lock(get_engine())
    scheduler = build_scheduler()

    def _stop(signum: int, _frame: FrameType | None) -> None:
        log.info("shutdown requested", extra={"signal": signum})
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("worker starting", extra={"jobs": [j.id for j in scheduler.get_jobs()]})
    try:
        scheduler.start()
    finally:
        lock.close()


if __name__ == "__main__":
    main()
