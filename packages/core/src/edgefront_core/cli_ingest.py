"""CLI (Daily Climate Report) ingest from api.weather.gov. Called by the worker only."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.metar_ingest import raw_hash
from edgefront_core.models import CliProduct, Station
from edgefront_core.nws_products import NwsProductLister, RawProduct, lookback
from edgefront_core.parsers.cli import parse_cli
from edgefront_core.source_health import record_failure, record_success
from edgefront_core.timeutil import utcnow

log = logging.getLogger("edgefront.cli")
SOURCE = "cli"
SOURCE_LABEL = "api.weather.gov/products (CLI)"


@dataclass
class CliResult:
    stations: int = 0
    new: int = 0
    decode_errors: int = 0
    failed_stations: int = 0
    latest_issued: datetime | None = None


def cli_row(st: Station, p: RawProduct, fetched_at: datetime) -> CliProduct:
    c = parse_cli(p.text)
    if c.location and st.cli_location and c.location != st.cli_location:
        c.errors.append(f"PIL location {c.location} != registry {st.cli_location}")
    return CliProduct(
        station_id=st.id,
        product_id=p.product_id,
        issuer=c.issuer or p.issuer,
        wmo_header=c.wmo_header or p.wmo_header,
        is_correction=c.is_correction,
        issued_at=p.issued_at,
        climate_date=c.climate_date,
        report_kind=c.kind,
        valid_as_of_local=c.valid_as_of_local,
        max_temp_f=c.max.value_f,
        max_time_local=c.max.time_local,
        min_temp_f=c.min.value_f,
        min_time_local=c.min.time_local,
        precip_in=c.precip_in,
        precip_trace=c.precip_trace,
        normal_high_f=c.max.normal_f,
        normal_low_f=c.min.normal_f,
        departure_high_f=c.max.departure_f,
        departure_low_f=c.min.departure_f,
        raw_text=p.text,
        raw_hash=raw_hash(p.text),
        decode_errors=c.errors or None,
        source=SOURCE_LABEL,
        fetched_at=fetched_at,
    )


def run_cli_ingest(
    factory: sessionmaker[Session],
    lister: NwsProductLister,
    *,
    now: Callable[[], datetime] = utcnow,
) -> CliResult:
    started = time.perf_counter()
    at = now()
    res = CliResult()
    errors: list[str] = []
    with session_scope(factory) as s:
        stations = list(
            s.scalars(select(Station).where(Station.active, Station.cli_location.is_not(None)))
        )
        known = {pid for (pid,) in s.execute(select(CliProduct.product_id))}
    for st in stations:
        res.stations += 1
        try:
            loc = st.cli_location or ""
            products = lister.new_products("CLI", loc, known, since=lookback(at))
        except Exception as exc:  # one station failing must not stop the others
            res.failed_stations += 1
            errors.append(f"{st.id}: {type(exc).__name__}")
            log.warning("cli fetch failed", extra={"station": st.id, "error": str(exc)[:200]})
            continue
        if not products:
            continue
        fetched_at = now()
        with session_scope(factory) as s:
            for p in products:
                row = cli_row(st, p, fetched_at)
                s.add(row)
                known.add(p.product_id)
                res.new += 1
                res.decode_errors += bool(row.decode_errors)
                if res.latest_issued is None or p.issued_at > res.latest_issued:
                    res.latest_issued = p.issued_at
    with session_scope(factory) as s:
        if res.failed_stations == res.stations and res.stations:
            record_failure(s, SOURCE, at, "; ".join(errors)[:500])
        else:
            record_success(
                s,
                SOURCE,
                at,
                last_item_time=res.latest_issued,
                notes=f"new={res.new} failed_stations={res.failed_stations}",
            )
    log.info(
        "cli ingest",
        extra={
            "source": SOURCE,
            "stations": res.stations,
            "count_new": res.new,
            "decode_errors": res.decode_errors,
            "failed_stations": res.failed_stations,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        },
    )
    return res
