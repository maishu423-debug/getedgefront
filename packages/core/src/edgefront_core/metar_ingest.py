"""METAR/SPECI ingest from aviationweather.gov (CONTEXT.md §4.1). Called by the worker only.

Verified 2026-11-24: `GET /api/data/metar?ids=…&format=json&hours=N` returns at most **400**
reports (newest first), so batches are split until each response is below the cap. Only the
corrected version of a report is returned once a COR exists; we link it to the original we
stored earlier, if any.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.climate import (
    DayBasis,
    climate_date,
    climate_day_bounds,
    high_events,
)
from edgefront_core.db import session_scope
from edgefront_core.http import get_with_retry
from edgefront_core.models import DailyHighEvent, MetarReport, SourceHealth, Station
from edgefront_core.parsers.metar import MetarParseError, parse_metar, resolve_observed_at
from edgefront_core.source_health import record_failure, record_success
from edgefront_core.timeutil import utcnow

log = logging.getLogger("edgefront.metar")

SOURCE = "metar"
SOURCE_LABEL = "aviationweather.gov/api/data/metar"
METAR_URL = "https://aviationweather.gov/api/data/metar"
RESPONSE_CAP = 400
BACKFILL_HOURS = 36
ROUTINE_HOURS = 3


def raw_hash(raw: str) -> str:
    return hashlib.sha256(" ".join(raw.split()).encode()).hexdigest()


# ---------------------------------------------------------------- fetch


def fetch_metars(
    client: httpx.Client,
    ids: Sequence[str],
    hours: int,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """All reports for `ids` over `hours`, splitting batches that hit the 400-report cap."""
    if not ids:
        return []
    r = get_with_retry(
        client,
        METAR_URL,
        params={"ids": ",".join(ids), "format": "json", "hours": str(hours)},
        sleep=sleep,
    )
    if r.status_code == 204:
        return []
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise ValueError("metar: expected a JSON list")
    if len(data) >= RESPONSE_CAP and len(ids) > 1:
        mid = len(ids) // 2
        return fetch_metars(client, ids[:mid], hours, sleep=sleep) + fetch_metars(
            client, ids[mid:], hours, sleep=sleep
        )
    if len(data) >= RESPONSE_CAP:
        log.warning("metar response at cap for a single station", extra={"ids": list(ids)})
    return data


def plan_batches(ids: Sequence[str], hours: int) -> list[list[str]]:
    """Batch sizes that stay well under the cap (~1.5 reports/h/station incl. SPECIs)."""
    per_station = max(1, int(hours * 1.6))
    size = max(1, min(len(ids), (RESPONSE_CAP * 3 // 4) // per_station))
    return [list(ids[i : i + size]) for i in range(0, len(ids), size)]


# ---------------------------------------------------------------- store


@dataclass
class IngestResult:
    fetched: int = 0
    new: int = 0
    dup: int = 0
    errors: int = 0
    unknown_station: int = 0
    corrections_linked: int = 0
    events_added: int = 0
    events_removed: int = 0
    latest_item_time: datetime | None = None
    affected_days: set[tuple[str, date]] = field(default_factory=set)


def _row(item: dict[str, Any], fetched_at: datetime) -> MetarReport:
    raw = str(item["rawOb"]).strip()
    m = parse_metar(raw)
    obs = None
    if isinstance(item.get("obsTime"), int):
        obs = datetime.fromtimestamp(item["obsTime"], UTC)
    from_raw = resolve_observed_at(m, obs or fetched_at)
    if obs is not None and obs != from_raw:
        log.warning("obsTime disagrees with raw text; using raw", extra={"raw": raw})
    return MetarReport(
        station_id=m.station,
        report_type=m.report_type,
        observed_at=from_raw,
        raw_text=raw,
        raw_hash=raw_hash(raw),
        is_correction=m.is_correction,
        temp_c=m.temp_c,
        dewpt_c=m.dewpt_c,
        temp_precision=m.temp_precision,
        wind_dir_deg=m.wind_dir_deg,
        wind_vrb=m.wind_vrb,
        wind_kt=m.wind_kt,
        gust_kt=m.gust_kt,
        vis_mi=m.vis_mi,
        sky=[s.as_dict() for s in m.sky],
        altim_inhg=m.altim_inhg,
        slp_hpa=m.slp_hpa,
        max6h_c=m.max6h_c,
        min6h_c=m.min6h_c,
        max24h_c=m.max24h_c,
        min24h_c=m.min24h_c,
        source=SOURCE_LABEL,
        fetched_at=fetched_at,
    )


def _utc(dt: datetime) -> datetime:
    # SQLite returns naive datetimes; everything we store is UTC.
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def store_reports(
    session: Session, items: list[dict[str, Any]], fetched_at: datetime
) -> IngestResult:
    res = IngestResult(fetched=len(items))
    stations = {s.id: s for s in session.scalars(select(Station).where(Station.active))}

    rows: list[MetarReport] = []
    for item in items:
        try:
            row = _row(item, fetched_at)
        except (MetarParseError, KeyError, ValueError) as exc:
            res.errors += 1
            log.warning("metar parse error", extra={"raw": item.get("rawOb"), "error": str(exc)})
            continue
        if row.station_id not in stations:
            res.unknown_station += 1
            continue
        rows.append(row)
    if not rows:
        return res

    lo = min(r.observed_at for r in rows)
    existing = list(
        session.scalars(
            select(MetarReport).where(
                MetarReport.station_id.in_({r.station_id for r in rows}),
                MetarReport.observed_at >= lo,
            )
        )
    )
    seen = {(e.station_id, _utc(e.observed_at), e.report_type, e.raw_hash) for e in existing}
    originals = {
        (e.station_id, _utc(e.observed_at), e.report_type): e
        for e in sorted(existing, key=lambda e: e.id)
        if not e.is_correction
    }

    for row in sorted(rows, key=lambda r: (r.observed_at, r.is_correction)):
        key = (row.station_id, row.observed_at, row.report_type, row.raw_hash)
        if key in seen:
            res.dup += 1
            continue
        seen.add(key)
        if row.is_correction:
            orig = originals.get(key[:3])
            if orig is not None:
                row.corrects_report_id = orig.id
                res.corrections_linked += 1
        else:
            originals.setdefault(key[:3], row)
        session.add(row)
        session.flush()  # assign id (needed for correction links within one batch)
        res.new += 1
        st = stations[row.station_id]
        res.affected_days.add((row.station_id, climate_date(row.observed_at, st.tz, _basis(st))))
        if res.latest_item_time is None or row.observed_at > res.latest_item_time:
            res.latest_item_time = row.observed_at
    return res


def _basis(st: Station) -> DayBasis:
    return "LOCAL" if st.day_basis == "LOCAL" else "LST"


# ---------------------------------------------------------------- new-high events


@dataclass(frozen=True)
class _ReportView:
    """Read-only copy with tz-aware times (SQLite returns naive datetimes)."""

    id: int
    observed_at: datetime
    report_type: str
    is_correction: bool
    temp_c: Decimal | None
    temp_precision: str | None
    max6h_c: Decimal | None

    @classmethod
    def of(cls, r: MetarReport) -> _ReportView:
        return cls(
            r.id,
            _utc(r.observed_at),
            r.report_type,
            r.is_correction,
            r.temp_c,
            r.temp_precision,
            r.max6h_c,
        )


def sync_high_events(session: Session, station: Station, day: date) -> tuple[int, int]:
    """Recompute the day's new-high events from stored reports and reconcile the table
    (handles late arrivals and corrections). Returns (added, removed)."""
    start, end = climate_day_bounds(day, station.tz, _basis(station))
    reports = list(
        session.scalars(
            select(MetarReport).where(
                MetarReport.station_id == station.id,
                MetarReport.observed_at >= start,
                MetarReport.observed_at < end + timedelta(hours=1),
            )
        )
    )
    views = [_ReportView.of(r) for r in reports]
    wanted = {(e.report_id, e.from_c, e.to_c): e for e in high_events(views, start, end)}
    current = list(
        session.scalars(
            select(DailyHighEvent).where(
                DailyHighEvent.station_id == station.id, DailyHighEvent.climate_date == day
            )
        )
    )
    have = {(c.report_id, c.from_c, c.to_c): c for c in current}
    removed = 0
    for key, row in have.items():
        if key not in wanted:
            session.delete(row)
            removed += 1
    added = 0
    for key, ev in wanted.items():
        if key not in have:
            session.add(
                DailyHighEvent(
                    station_id=station.id,
                    climate_date=day,
                    from_c=ev.from_c,
                    to_c=ev.to_c,
                    report_id=ev.report_id,
                    observed_at=ev.observed_at,
                )
            )
            added += 1
    return added, removed


# ---------------------------------------------------------------- job


def choose_hours(last_success: datetime | None, now: datetime) -> int:
    """Backfill 36 h on first run or after an outage; otherwise a short window."""
    if last_success is None or now - _utc(last_success) > timedelta(hours=ROUTINE_HOURS - 1):
        return BACKFILL_HOURS
    return ROUTINE_HOURS


def run_metar_ingest(
    factory: sessionmaker[Session],
    client: httpx.Client,
    *,
    now: Callable[[], datetime] = utcnow,
    hours: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> IngestResult:
    started = time.perf_counter()
    attempt_at = now()
    try:
        with session_scope(factory) as s:
            ids = [sid for (sid,) in s.execute(select(Station.id).where(Station.active))]
            health = s.get(SourceHealth, SOURCE)
            h = hours or choose_hours(health.last_success_at if health else None, attempt_at)
        items: list[dict[str, Any]] = []
        for batch in plan_batches(ids, h):
            items += fetch_metars(client, batch, h, sleep=sleep)
        fetched_at = now()
        with session_scope(factory) as s:
            res = store_reports(s, items, fetched_at)
            stations = {st.id: st for st in s.scalars(select(Station))}
            for sid, day in sorted(res.affected_days):
                a, r = sync_high_events(s, stations[sid], day)
                res.events_added += a
                res.events_removed += r
            latest = res.latest_item_time
            if latest is None:
                latest_db = s.scalar(
                    select(MetarReport.observed_at).order_by(MetarReport.observed_at.desc())
                )
                latest = _utc(latest_db) if latest_db else None
            record_success(
                s,
                SOURCE,
                attempt_at,
                last_item_time=latest,
                notes=f"hours={h} fetched={res.fetched} new={res.new} dup={res.dup}",
            )
    except Exception as exc:
        log.exception("metar ingest failed", extra={"source": SOURCE})
        try:
            with session_scope(factory) as s:
                record_failure(s, SOURCE, attempt_at, f"{type(exc).__name__}: {exc}")
        except Exception:  # DB down; the log line above is the record
            log.error("could not record metar failure", extra={"source": SOURCE})
        raise
    log.info(
        "metar ingest",
        extra={
            "source": SOURCE,
            "hours": h,
            "count_fetched": res.fetched,
            "count_new": res.new,
            "count_dup": res.dup,
            "count_errors": res.errors,
            "corrections_linked": res.corrections_linked,
            "events_added": res.events_added,
            "events_removed": res.events_removed,
            "latest_item_time": res.latest_item_time.isoformat() if res.latest_item_time else None,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        },
    )
    return res
