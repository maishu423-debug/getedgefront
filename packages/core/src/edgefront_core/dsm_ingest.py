"""DSM ingest with pluggable fetchers (CONTEXT.md §4.2, owner Q14/Q17). Called by the worker only.

Sources: api.weather.gov for stations with `dsm_source = nws_api` (KNYC/KMSP/KSAT); the Iowa
Environmental Mesonet (IEM) AFOS archive for `dsm_source = iem`. A future NWWS-OI feed is just
another `DsmFetcher`.

IEM politeness: one small list request per station per run (every ~12 min with jitter), the
product text only for products we have not stored, a generic User-Agent (no personal contact
to third parties), a pause between calls and exponential backoff on 429/5xx. Never called from
a web request.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.http import get_with_retry
from edgefront_core.metar_ingest import raw_hash
from edgefront_core.models import DsmProduct, Station
from edgefront_core.nws_products import NwsProductLister, RawProduct, lookback
from edgefront_core.parsers.dsm import body_of, climate_date_for, parse_dsm
from edgefront_core.source_health import record_failure, record_success
from edgefront_core.timeutil import utcnow

log = logging.getLogger("edgefront.dsm")

HEALTH_KEY = {"nws_api": "dsm_nws", "iem": "dsm_iem"}
IEM = "https://mesonet.agron.iastate.edu"
IEM_UA = {"User-Agent": "EdgeFront/1.0 (getedgefront.com)"}


class DsmFetcher(Protocol):
    source: str  # value stored in dsm_products.source

    def new_products(
        self, location: str, known_ids: set[str], now: datetime, first_run: bool
    ) -> list[RawProduct]: ...


class NwsApiDsmFetcher:
    source = "nws_api"

    def __init__(self, lister: NwsProductLister) -> None:
        self.lister = lister
        self.seen: set[str] = set()

    def new_products(
        self, location: str, known_ids: set[str], now: datetime, first_run: bool
    ) -> list[RawProduct]:
        got = self.lister.new_products("DSM", location, known_ids | self.seen, since=lookback(now))
        self.seen.update(p.product_id for p in got)
        return got


class IemDsmFetcher:
    source = "iem"

    def __init__(
        self,
        client: httpx.Client,
        *,
        sleep: Callable[[float], None] = time.sleep,
        pause_s: float = 2.0,
        backoff_s: float = 5.0,
    ) -> None:
        self.client = client
        self.sleep = sleep
        self.pause_s = pause_s
        self.backoff_s = backoff_s
        # Products already fetched by this process (incl. duplicates that were not stored).
        self.seen: set[str] = set()

    @staticmethod
    def make_client() -> httpx.Client:
        return httpx.Client(headers=IEM_UA, timeout=30, follow_redirects=True)

    def _get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        self.sleep(self.pause_s)
        r = get_with_retry(
            self.client, url, params=params, base_delay=self.backoff_s, sleep=self.sleep
        )
        r.raise_for_status()
        return r

    def new_products(
        self, location: str, known_ids: set[str], now: datetime, first_run: bool
    ) -> list[RawProduct]:
        pil = f"DSM{location}"
        days = [now.date()]
        if first_run or now.hour < 2:  # catch products entered late on the previous UTC day
            days.append((now - timedelta(days=1)).date())
        out: list[RawProduct] = []
        for d in days:
            rows = (
                self._get(f"{IEM}/api/1/nws/afos/list.json", {"pil": pil, "date": d.isoformat()})
                .json()
                .get("data")
                or []
            )
            for row in rows:
                pid = str(row["product_id"])
                if pid in known_ids or pid in self.seen:
                    continue
                text = self._get(f"{IEM}/api/1/nwstext/{pid}").text
                self.seen.add(pid)
                parts = pid.split("-")  # 202611240516-KZNY-CDUS27-DSMLGA
                out.append(
                    RawProduct(
                        product_id=pid,
                        issued_at=datetime.fromisoformat(row["entered"].replace("Z", "+00:00")),
                        issuer=row.get("cccc") or (parts[1] if len(parts) > 1 else None),
                        wmo_header=" ".join(parts[2:3] + parts[1:2]) if len(parts) >= 3 else None,
                        text=text,
                        url=f"{IEM}/api/1/nwstext/{pid}",
                    )
                )
        return out


def dsm_hash(text: str) -> str:
    """Hash of the coded body only, so the same DSM from two transmissions dedupes."""
    return raw_hash(body_of(text) or text)


def dsm_row(st: Station, source: str, p: RawProduct, fetched_at: datetime) -> DsmProduct:
    d = parse_dsm(p.text)
    errors = list(d.errors)
    if d.station and d.station != st.id:
        errors.append(f"product is for {d.station}, not {st.id}")
    return DsmProduct(
        station_id=st.id,
        product_id=p.product_id,
        source=source,
        issuer=p.issuer,
        wmo_header=p.wmo_header,
        issued_at=p.issued_at,
        climate_date=climate_date_for(d, p.issued_at),
        report_kind=d.kind,
        issue_key=d.issue_key,
        is_correction=d.is_correction,
        max_temp_f=d.max_f,
        max_time_local=d.max_time_local,
        min_temp_f=d.min_f,
        min_time_local=d.min_time_local,
        precip_in=d.precip_in,
        precip_trace=d.precip_trace,
        peak_wind_dir=d.wind.dir_deg,
        peak_wind_speed=d.wind.speed_mph,
        peak_wind_time_local=d.wind.time_local,
        peak_gust_dir=d.gust.dir_deg,
        peak_gust_speed=d.gust.speed_mph,
        peak_gust_time_local=d.gust.time_local,
        wind_speed_unit="mph" if d.gust.speed_mph is not None or d.wind.speed_mph else None,
        raw_text=p.text,
        raw_hash=dsm_hash(p.text),
        decode_errors=errors or None,
        fetched_at=fetched_at,
    )


@dataclass
class SourceStats:
    stations: int = 0
    failed: int = 0
    new: int = 0
    dup: int = 0
    decode_errors: int = 0
    latest_issued: datetime | None = None
    errors: list[str] = field(default_factory=list)


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def run_dsm_ingest(
    factory: sessionmaker[Session],
    fetchers: Mapping[str, DsmFetcher],
    *,
    now: Callable[[], datetime] = utcnow,
) -> dict[str, SourceStats]:
    started = time.perf_counter()
    at = now()
    stats: dict[str, SourceStats] = {}
    with session_scope(factory) as s:
        stations = list(
            s.scalars(
                select(Station).where(
                    Station.active,
                    Station.dsm_source.is_not(None),
                    Station.dsm_location.is_not(None),
                )
            )
        )
        since = at - timedelta(days=7)
        known_rows = s.execute(
            select(
                DsmProduct.station_id,
                DsmProduct.product_id,
                DsmProduct.climate_date,
                DsmProduct.issue_key,
                DsmProduct.raw_hash,
            ).where(DsmProduct.issued_at >= since)
        ).all()
    known_ids: dict[str, set[str]] = {}
    known_keys: set[tuple[str, object, str, str]] = set()
    for sid, pid, cdate, ikey, rhash in known_rows:
        known_ids.setdefault(sid, set()).add(pid)
        known_keys.add((sid, cdate, ikey, rhash))

    for st in stations:
        src = st.dsm_source or ""
        fetcher = fetchers.get(src)
        stat = stats.setdefault(src, SourceStats())
        stat.stations += 1
        if fetcher is None:
            stat.failed += 1
            stat.errors.append(f"{st.id}: no fetcher for {src}")
            continue
        ids = known_ids.setdefault(st.id, set())
        try:
            products = fetcher.new_products(st.dsm_location or "", ids, at, first_run=not ids)
        except Exception as exc:  # one station failing must not stop the others
            stat.failed += 1
            stat.errors.append(f"{st.id}: {type(exc).__name__}")
            log.warning(
                "dsm fetch failed", extra={"station": st.id, "source": src, "error": str(exc)[:200]}
            )
            continue
        if not products:
            continue
        fetched_at = now()
        with session_scope(factory) as s:
            for p in sorted(products, key=lambda p: p.issued_at):
                ids.add(p.product_id)
                row = dsm_row(st, fetcher.source, p, fetched_at)
                key = (st.id, row.climate_date, row.issue_key, row.raw_hash)
                if key in known_keys:
                    stat.dup += 1
                    continue
                known_keys.add(key)
                s.add(row)
                stat.new += 1
                stat.decode_errors += bool(row.decode_errors)
                if stat.latest_issued is None or p.issued_at > stat.latest_issued:
                    stat.latest_issued = p.issued_at

    with session_scope(factory) as s:
        for src, stat in stats.items():
            health_key = HEALTH_KEY.get(src, f"dsm_{src}")
            if stat.stations and stat.failed == stat.stations:
                record_failure(s, health_key, at, "; ".join(stat.errors)[:500])
            else:
                record_success(
                    s,
                    health_key,
                    at,
                    last_item_time=stat.latest_issued,
                    notes=f"new={stat.new} dup={stat.dup} failed={stat.failed}",
                )
    for src, stat in stats.items():
        log.info(
            "dsm ingest",
            extra={
                "source": HEALTH_KEY.get(src, src),
                "stations": stat.stations,
                "count_new": stat.new,
                "count_dup": stat.dup,
                "decode_errors": stat.decode_errors,
                "failed_stations": stat.failed,
                "latest_item_time": stat.latest_issued.isoformat() if stat.latest_issued else None,
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )
    return stats
