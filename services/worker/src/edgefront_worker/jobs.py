"""Scheduled ingest jobs. Each job is idempotent and never raises into the scheduler."""

from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.cli_ingest import run_cli_ingest
from edgefront_core.dsm_ingest import (
    DsmFetcher,
    IemDsmFetcher,
    NwsApiDsmFetcher,
    run_dsm_ingest,
)
from edgefront_core.forecast_ingest import run_forecast_ingest
from edgefront_core.http import make_client
from edgefront_core.metar_ingest import run_metar_ingest
from edgefront_core.nws_products import NwsProductLister

log = logging.getLogger("edgefront.worker.jobs")


def metar_job(factory: sessionmaker[Session]) -> None:
    try:
        with make_client() as client:
            run_metar_ingest(factory, client)
    except Exception:  # already logged + recorded in source_health by run_metar_ingest
        log.warning("metar job ended with an error", extra={"source": "metar"})


class ProductJobs:
    """Holds long-lived clients so conditional-request state (Last-Modified) survives runs."""

    def __init__(self) -> None:
        self.nws: httpx.Client = make_client()
        self.iem: httpx.Client = IemDsmFetcher.make_client()
        self.lister = NwsProductLister(self.nws)
        self.dsm_fetchers: dict[str, DsmFetcher] = {
            "nws_api": NwsApiDsmFetcher(self.lister),
            "iem": IemDsmFetcher(self.iem),
        }

    def cli(self, factory: sessionmaker[Session]) -> None:
        try:
            run_cli_ingest(factory, self.lister)
        except Exception:
            log.exception("cli job failed", extra={"source": "cli"})

    def dsm(self, factory: sessionmaker[Session]) -> None:
        try:
            run_dsm_ingest(factory, self.dsm_fetchers)
        except Exception:
            log.exception("dsm job failed", extra={"source": "dsm"})

    def forecast(self, factory: sessionmaker[Session]) -> None:
        try:
            run_forecast_ingest(factory, self.nws)
        except Exception:
            log.exception("forecast job failed", extra={"source": "forecast"})
