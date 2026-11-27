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
from edgefront_core.model_text_ingest import PfmIngest, TextModelIngest
from edgefront_core.native_unit_check import run_native_unit_check
from edgefront_core.nws_products import NwsProductLister
from edgefront_core.retention import run_retention
from edgefront_core.settings import get_settings
from edgefront_core.timeutil import utcnow
from edgefront_worker.grib.ingest import GribModelIngest
from edgefront_worker.hfmetar import HfmetarIngest

log = logging.getLogger("edgefront.worker.jobs")


def retention_job(factory: sessionmaker[Session]) -> None:
    try:
        run_retention(factory, warn_bytes=get_settings().db_size_warn_bytes)
    except Exception:  # logged + recorded in source_health by run_retention
        log.warning("retention job ended with an error", extra={"source": "retention"})


def native_unit_job(factory: sessionmaker[Session]) -> None:
    """Weekly: does each station still measure in the unit the registry says? (Q36)"""
    try:
        run_native_unit_check(factory, utcnow())
    except Exception:
        log.exception("native unit check failed", extra={"source": "native_unit_check"})


def metar_job(factory: sessionmaker[Session]) -> None:
    try:
        with make_client() as client:
            run_metar_ingest(factory, client)
    except Exception:  # already logged + recorded in source_health by run_metar_ingest
        log.warning("metar job ended with an error", extra={"source": "metar"})


class HfmetarJob:
    """v2 Phase 9: one long-lived client for the LDM API (keep-alive, 60 s cadence)."""

    def __init__(self) -> None:
        s = get_settings()
        self.client: httpx.Client = make_client(timeout=30)
        self.ingest = HfmetarIngest(
            self.client,
            s.ldm_api_base_url,
            s.madis_api_token,
            max_files=s.hf_max_files_per_run,
            backfill_hours=s.hf_backfill_hours,
            stale_minutes=s.hf_stale_minutes,
        )

    def __call__(self, factory: sessionmaker[Session]) -> None:
        try:
            self.ingest.run(factory)
        except Exception:
            log.exception("hfmetar job failed", extra={"source": "hfmetar"})


class ProductJobs:
    """Holds long-lived clients so conditional-request state (Last-Modified) survives runs."""

    def __init__(self) -> None:
        self.nws: httpx.Client = make_client()
        self.iem: httpx.Client = IemDsmFetcher.make_client()
        self.lister = NwsProductLister(self.nws)
        self.nomads: httpx.Client = make_client(timeout=120)  # 28 MB NBM bulletins
        self.text_models = TextModelIngest(self.nomads)
        self.grib_client: httpx.Client = make_client(timeout=60)
        self.grib = GribModelIngest(self.grib_client)
        self.pfm = PfmIngest(self.lister)
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

    def models_text(self, factory: sessionmaker[Session]) -> None:
        """NBM, GFS-MOS, LAMP (NOMADS) then PFM. One model failing never stops the others."""
        for model in ("lamp", "nbm", "gfs_mos"):
            try:
                self.text_models.run(factory, model)
            except Exception:  # logged + recorded in source_health by the ingest
                log.warning("model text job error", extra={"source": f"model_{model}"})
        try:
            self.pfm.run(factory)
        except Exception:
            log.warning("pfm job error", extra={"source": "model_pfm"})

    def models_grib(self, factory: sessionmaker[Session]) -> None:
        """GFS, IFS, AIFS (one at a time, so GRIB memory never stacks). Never raises."""
        for model in ("aifs", "ifs", "gfs"):
            try:
                self.grib.run(factory, model)
            except Exception:  # logged + recorded in source_health by the ingest
                log.warning("grib job error", extra={"source": f"model_{model}"})
