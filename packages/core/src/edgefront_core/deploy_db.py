"""Pre-deploy step for the `api` service on Railway: `python -m edgefront_core.deploy_db`.

Applies all Alembic migrations, then seeds the station registry from data/stations.yaml. Both
steps are idempotent, so running this before every deploy is safe; a failure stops the deploy
(the previous version keeps serving). One JSON log line per step.
"""

from __future__ import annotations

import logging
import time

from edgefront_core import migrate, seed
from edgefront_core.logs import configure_logging
from edgefront_core.settings import get_settings

log = logging.getLogger("edgefront.deploy_db")


def main() -> None:
    configure_logging(get_settings().log_level)
    t = time.monotonic()
    migrate.upgrade("head")
    log.info("migrations applied", extra={"seconds": round(time.monotonic() - t, 2)})
    t = time.monotonic()
    seed.main([])
    log.info("registry seeded", extra={"seconds": round(time.monotonic() - t, 2)})


if __name__ == "__main__":
    main()
