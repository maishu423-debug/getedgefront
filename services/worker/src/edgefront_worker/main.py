"""Worker entry point: `python -m edgefront_worker.main`."""

from __future__ import annotations

import logging
import signal
from types import FrameType

from apscheduler.schedulers.blocking import BlockingScheduler

from edgefront_core.db import get_engine, make_sessionmaker
from edgefront_core.logs import configure_logging
from edgefront_core.settings import get_settings
from edgefront_core.timeutil import utcnow
from edgefront_worker.heartbeat import heartbeat

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
    return scheduler


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    scheduler = build_scheduler()

    def _stop(signum: int, _frame: FrameType | None) -> None:
        log.info("shutdown requested", extra={"signal": signum})
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("worker starting", extra={"jobs": [j.id for j in scheduler.get_jobs()]})
    scheduler.start()


if __name__ == "__main__":
    main()
