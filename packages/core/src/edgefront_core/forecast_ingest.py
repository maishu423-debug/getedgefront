"""NWS gridpoint forecast + hourly ingest (CONTEXT.md §4.3). Called by the worker only.

Caching (verified 2026-11-24): responses carry `Cache-Control: public, max-age=3598…`,
`Expires` and `Last-Modified`. A station is skipped while its stored expiry is in the future;
after that the request is conditional (`If-Modified-Since`), and a 304 only extends the expiry.
5xx/429 are retried with exponential backoff (shared HTTP client).
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.http import get_with_retry
from edgefront_core.models import NwsForecast, Station
from edgefront_core.source_health import record_failure, record_success
from edgefront_core.timeutil import utcnow

log = logging.getLogger("edgefront.forecast")
SOURCE = "forecast"
SOURCE_LABEL = "api.weather.gov/gridpoints"
NWS = "https://api.weather.gov"
GEO = {"Accept": "application/geo+json"}
KEEP_PER_STATION = 3
HOURLY_KEEP = 48
DEFAULT_TTL = timedelta(minutes=30)


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def expiry(resp: httpx.Response, now: datetime) -> datetime:
    """When the response may be refreshed: Cache-Control max-age, else Expires, else +30 min."""
    cc = resp.headers.get("Cache-Control", "")
    if m := re.search(r"max-age=(\d+)", cc):
        return now + timedelta(seconds=int(m.group(1)))
    if exp := resp.headers.get("Expires"):
        try:
            return parsedate_to_datetime(exp).astimezone(UTC)
        except (TypeError, ValueError):
            pass
    return now + DEFAULT_TTL


@dataclass
class Fetched:
    status: int  # 200 | 304 | 0 (skipped: not expired)
    doc: dict[str, Any] | None = None
    expires_at: datetime | None = None
    last_modified: str | None = None


def _fetch(
    client: httpx.Client,
    url: str,
    expires_at: datetime | None,
    last_modified: str | None,
    now: datetime,
    sleep: Callable[[float], None],
) -> Fetched:
    if expires_at is not None and _utc(expires_at) > now:  # type: ignore[operator]
        return Fetched(0)
    headers = dict(GEO)
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    r = get_with_retry(client, url, headers=headers, sleep=sleep)
    if r.status_code == 304:
        return Fetched(304, expires_at=expiry(r, now), last_modified=last_modified)
    r.raise_for_status()
    return Fetched(200, r.json(), expiry(r, now), r.headers.get("Last-Modified"))


def _ts(doc: dict[str, Any] | None, key: str) -> datetime | None:
    v = (doc or {}).get("properties", {}).get(key)
    return datetime.fromisoformat(v) if isinstance(v, str) else None


@dataclass
class ForecastResult:
    stations: int = 0
    updated: int = 0
    not_modified: int = 0
    skipped_fresh: int = 0
    failed: int = 0


def refresh_station(
    session: Session,
    client: httpx.Client,
    st: Station,
    now: datetime,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Returns 'updated' | 'not_modified' | 'fresh'."""
    base = f"{NWS}/gridpoints/{st.nws_office}/{st.grid_x},{st.grid_y}"
    prev = session.scalars(
        select(NwsForecast)
        .where(NwsForecast.station_id == st.id)
        .order_by(NwsForecast.fetched_at.desc(), NwsForecast.id.desc())
    ).first()
    f = _fetch(
        client,
        f"{base}/forecast",
        prev.forecast_expires_at if prev else None,
        prev.forecast_last_modified if prev else None,
        now,
        sleep,
    )
    h = _fetch(
        client,
        f"{base}/forecast/hourly",
        prev.hourly_expires_at if prev else None,
        prev.hourly_last_modified if prev else None,
        now,
        sleep,
    )
    if f.status == 0 and h.status == 0:
        return "fresh"
    if f.status != 200 and h.status != 200:
        if prev is None:  # cannot happen (a 304 needs a previous Last-Modified)
            return "not_modified"
        prev.fetched_at = now
        if f.expires_at:
            prev.forecast_expires_at = f.expires_at
        if h.expires_at:
            prev.hourly_expires_at = h.expires_at
        return "not_modified"

    periods = (f.doc or {}).get("properties", {}).get("periods") if f.status == 200 else None
    hourly = (h.doc or {}).get("properties", {}).get("periods") if h.status == 200 else None
    row = NwsForecast(
        station_id=st.id,
        office=st.nws_office or "",
        generated_at=_ts(f.doc, "generatedAt") if f.status == 200 else (prev and prev.generated_at),
        update_time=_ts(f.doc, "updateTime") if f.status == 200 else (prev and prev.update_time),
        hourly_update_time=_ts(h.doc, "updateTime")
        if h.status == 200
        else (prev and prev.hourly_update_time),
        periods=periods if periods is not None else (prev.periods if prev else None),
        hourly=hourly[:HOURLY_KEEP] if hourly is not None else (prev.hourly if prev else None),
        forecast_expires_at=f.expires_at or (prev and prev.forecast_expires_at),
        hourly_expires_at=h.expires_at or (prev and prev.hourly_expires_at),
        forecast_last_modified=f.last_modified or (prev and prev.forecast_last_modified),
        hourly_last_modified=h.last_modified or (prev and prev.hourly_last_modified),
        source=SOURCE_LABEL,
        fetched_at=now,
    )
    session.add(row)
    session.flush()
    keep = [
        i
        for (i,) in session.execute(
            select(NwsForecast.id)
            .where(NwsForecast.station_id == st.id)
            .order_by(NwsForecast.fetched_at.desc(), NwsForecast.id.desc())
            .limit(KEEP_PER_STATION)
        )
    ]
    session.execute(
        delete(NwsForecast).where(NwsForecast.station_id == st.id, NwsForecast.id.not_in(keep))
    )
    return "updated"


def run_forecast_ingest(
    factory: sessionmaker[Session],
    client: httpx.Client,
    *,
    now: Callable[[], datetime] = utcnow,
    sleep: Callable[[float], None] = time.sleep,
    pause_s: float = 0.25,
) -> ForecastResult:
    started = time.perf_counter()
    at = now()
    res = ForecastResult()
    errors: list[str] = []
    with session_scope(factory) as s:
        ids = [
            sid
            for (sid,) in s.execute(
                select(Station.id).where(
                    Station.active, Station.nws_office.is_not(None), Station.grid_x.is_not(None)
                )
            )
        ]
    for sid in ids:
        res.stations += 1
        try:
            with session_scope(factory) as s:
                st = s.get(Station, sid)
                if st is None:
                    continue
                outcome = refresh_station(s, client, st, now(), sleep)
        except Exception as exc:  # one station failing must not stop the others
            res.failed += 1
            errors.append(f"{sid}: {type(exc).__name__}")
            log.warning("forecast fetch failed", extra={"station": sid, "error": str(exc)[:200]})
            continue
        if outcome == "updated":
            res.updated += 1
            sleep(pause_s)
        elif outcome == "not_modified":
            res.not_modified += 1
            sleep(pause_s)
        else:
            res.skipped_fresh += 1
    with session_scope(factory) as s:
        if res.stations and res.failed == res.stations:
            record_failure(s, SOURCE, at, "; ".join(errors)[:500])
        else:
            record_success(
                s,
                SOURCE,
                at,
                last_item_time=at,
                notes=f"updated={res.updated} 304={res.not_modified} fresh={res.skipped_fresh} "
                f"failed={res.failed}",
            )
    log.info(
        "forecast ingest",
        extra={
            "source": SOURCE,
            "stations": res.stations,
            "updated": res.updated,
            "not_modified": res.not_modified,
            "skipped_fresh": res.skipped_fresh,
            "failed": res.failed,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        },
    )
    return res
