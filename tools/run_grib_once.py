"""Run one GRIB model ingest once in this process and print its summary (incl. peak memory).

    DATABASE_URL=... uv run python tools/run_grib_once.py gfs|ifs|aifs

Used for the Phase 5 memory measurement: one model per fresh process, so the peak RSS is the
job's own.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from edgefront_core.db import get_engine, make_sessionmaker
from edgefront_core.http import make_client
from edgefront_core.logs import configure_logging
from edgefront_worker.grib.ingest import GribModelIngest


def main() -> None:
    configure_logging()
    factory = make_sessionmaker(get_engine())
    with make_client(timeout=60) as client:
        summary = GribModelIngest(client).run(factory, sys.argv[1])
    print(json.dumps(asdict(summary), default=str))


if __name__ == "__main__":
    main()
