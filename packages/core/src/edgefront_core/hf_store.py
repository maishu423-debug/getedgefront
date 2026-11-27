"""5-minute HFMETAR data (v2 Phase 9): storage, latency, rounding check, 5-minute high/low so far.

The netCDF parser lives in the worker (it needs scipy). Everything here works on plain readings,
so the API and the tests need no netCDF stack. Format and grids: docs/formats/hfmetar.md.

- Upsert by (station_id, observed_at). A value change (row_hash differs) updates the values and
  bumps `revision`; a QC-only change (the normal case: MADIS revises QC letters as later readings
  arrive) updates `qc` and `updated_at` only. First-seen stamps (`source_file`,
  `file_modified_at`, `fetched_at`, `ingested_at`) are never overwritten.
- QC-failed (owner rule, B6): temperature data descriptor `X` (rejected), `Q` (questioned) or `B`
  (subjective bad). Stored with their flags; left out of the 5-minute high/low and counted.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from edgefront_core.models import HfObservation, MetarReport, Station
from edgefront_core.timeutil import as_utc
from edgefront_core.units import f_to_c, temp_value

log = logging.getLogger("edgefront.hfmetar")

SOURCE = "hfmetar"
QC_FAILED = frozenset({"X", "Q", "B"})
VALUE_FIELDS = (
    "temp_c", "temp_precision", "dewpt_c", "wind_dir_deg", "wind_kt", "gust_kt", "altim_inhg",
    "vis_mi", "precip_in",
)  # fmt: skip


@dataclass(frozen=True)
class HfReading:
    """One parsed 5-minute observation, already snapped to its grid (or flagged off grid)."""

    station_id: str
    observed_at: datetime
    received_at: datetime | None = None
    temp_c: Decimal | None = None
    temp_precision: str | None = None  # whole_c | tenths_c | off_grid
    dewpt_c: Decimal | None = None
    wind_dir_deg: int | None = None
    wind_kt: int | None = None
    gust_kt: int | None = None
    altim_inhg: Decimal | None = None
    vis_mi: Decimal | None = None
    precip_in: Decimal | None = None
    qc: dict[str, Any] = field(default_factory=dict)


def _canon(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return format(v.normalize(), "f")  # 17, 17.0 and 17.00 hash alike
    return str(v)


def row_hash(r: object) -> str:
    """sha256 of the measured values (not QC, not time stamps)."""
    return hashlib.sha256(
        "|".join(_canon(getattr(r, f)) for f in VALUE_FIELDS).encode()
    ).hexdigest()


@dataclass
class UpsertResult:
    new: int = 0
    revised: int = 0  # a measured value changed (revision bumped)
    qc_changed: int = 0  # QC flags only
    unchanged: int = 0
    latest_observed_at: datetime | None = None


def upsert_readings(
    session: Session,
    readings: Sequence[HfReading],
    *,
    source_file: str,
    file_modified_at: datetime | None,
    fetched_at: datetime,
    now: datetime,
) -> UpsertResult:
    res = UpsertResult()
    if not readings:
        return res
    ids = sorted({r.station_id for r in readings})
    lo = min(r.observed_at for r in readings)
    hi = max(r.observed_at for r in readings)
    existing = {
        (row.station_id, as_utc(row.observed_at)): row
        for row in session.scalars(
            select(HfObservation).where(
                HfObservation.station_id.in_(ids),
                HfObservation.observed_at >= lo,
                HfObservation.observed_at <= hi,
            )
        )
    }
    for r in readings:
        h = row_hash(r)
        res.latest_observed_at = max(res.latest_observed_at or r.observed_at, r.observed_at)
        row = existing.get((r.station_id, r.observed_at))
        if row is None:
            row = HfObservation(
                station_id=r.station_id,
                observed_at=r.observed_at,
                **{f: getattr(r, f) for f in VALUE_FIELDS},
                qc=r.qc,
                source_file=source_file,
                received_at=r.received_at,
                file_modified_at=file_modified_at,
                fetched_at=fetched_at,
                ingested_at=now,
                updated_at=now,
                row_hash=h,
                revision=0,
            )
            session.add(row)
            existing[(r.station_id, r.observed_at)] = row
            res.new += 1
            continue
        changed = False
        if row.row_hash != h:
            old = {f: _canon(getattr(row, f)) for f in VALUE_FIELDS}
            for f in VALUE_FIELDS:
                setattr(row, f, getattr(r, f))
            row.row_hash = h
            row.revision = (row.revision or 0) + 1
            res.revised += 1
            changed = True
            log.info(
                "hfmetar value revised",
                extra={
                    "source": SOURCE,
                    "station": r.station_id,
                    "observed_at": r.observed_at.isoformat(),
                    "revision": row.revision,
                    "old": old,
                    "new": {f: _canon(getattr(r, f)) for f in VALUE_FIELDS},
                    "file": source_file,
                },
            )
        if (row.qc or {}) != r.qc:
            row.qc = r.qc
            if not changed:
                res.qc_changed += 1
            changed = True
        if row.received_at is None and r.received_at is not None:
            row.received_at = r.received_at
        if changed:
            row.updated_at = now
        else:
            res.unchanged += 1
    session.flush()
    return res


def last_ingested_at(session: Session) -> datetime | None:
    v = session.scalar(select(func.max(HfObservation.ingested_at)))
    return as_utc(v) if v else None


# ---------------------------------------------------------------- latency (B5/B8)

STAGES = ("received", "file_modified", "fetched", "ingested")


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile (no interpolation: every result is a real measured delay)."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(q * len(s)) - 1)]


@dataclass
class StageStats:
    count: int
    p50_s: float | None
    p95_s: float | None


@dataclass
class LatencyReport:
    window_hours: int
    rows: int
    excluded_late: int  # first fetched more than `late_after` after observation (backfill/outage)
    overall: dict[str, StageStats]
    per_station: dict[str, dict[str, StageStats]]


def _stats(vals: Sequence[float]) -> StageStats:
    p50, p95 = percentile(vals, 0.50), percentile(vals, 0.95)
    return StageStats(len(vals), None if p50 is None else round(p50, 1),
                      None if p95 is None else round(p95, 1))  # fmt: skip


def latency_report(
    session: Session,
    now: datetime,
    *,
    hours: int = 6,
    late_after: timedelta = timedelta(minutes=60),
) -> LatencyReport:
    """Delay from observation to each stage (MADIS received → LDM file modified → our fetch →
    our insert), P50/P95 per station and overall, over readings observed in the last `hours`.
    Readings we first fetched more than `late_after` after their observation (first-run backfill,
    or catching up after an outage) are counted in `excluded_late`, not in the percentiles."""
    q = select(
        HfObservation.station_id, HfObservation.observed_at, HfObservation.received_at,
        HfObservation.file_modified_at, HfObservation.fetched_at, HfObservation.ingested_at,
    ).where(HfObservation.observed_at >= now - timedelta(hours=hours))  # fmt: skip
    overall: dict[str, list[float]] = defaultdict(list)
    per: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    rows = late = 0
    for sid, obs, rec, mod, fet, ing in session.execute(q):
        rows += 1
        obs = as_utc(obs)
        if as_utc(fet) - obs > late_after:
            late += 1
            continue
        for stage, t in zip(STAGES, (rec, mod, fet, ing), strict=True):
            if t is None:
                continue
            d = (as_utc(t) - obs).total_seconds()
            overall[stage].append(d)
            per[sid][stage].append(d)
    return LatencyReport(
        window_hours=hours,
        rows=rows,
        excluded_late=late,
        overall={st: _stats(overall[st]) for st in STAGES},
        per_station={sid: {st: _stats(v[st]) for st in STAGES} for sid, v in sorted(per.items())},
    )


def stations_reporting(session: Session, now: datetime, minutes: int = 30) -> list[str]:
    q = (
        select(HfObservation.station_id)
        .where(HfObservation.observed_at >= now - timedelta(minutes=minutes))
        .distinct()
    )
    return sorted(session.scalars(q))


# ---------------------------------------------------------------- rounding check (B2 item 5)


@dataclass
class RoundingCheck:
    pairs: int = 0
    matches: int = 0
    mismatches: list[dict[str, Any]] = field(default_factory=list)


def rounding_check(session: Session, since: datetime) -> RoundingCheck:
    """Pair 5-minute whole-°C readings with METAR/SPECI T-groups (tenths °C) at the same station
    and minute. Expected: the 5-minute °C is the nearest whole °C of the station's whole-°F
    reading (NWS half-up of the T-group). °C stations (native_temp_unit C) are skipped."""
    q = (
        select(HfObservation.station_id, HfObservation.observed_at, HfObservation.temp_c,
               MetarReport.temp_c)
        .join(MetarReport, and_(MetarReport.station_id == HfObservation.station_id,
                                MetarReport.observed_at == HfObservation.observed_at))
        .join(Station, Station.id == HfObservation.station_id)
        .where(
            HfObservation.observed_at >= since,
            HfObservation.temp_precision == "whole_c",
            HfObservation.temp_c.is_not(None),
            MetarReport.temp_precision == "tenths",
            MetarReport.temp_c.is_not(None),
            Station.native_temp_unit == "F",
        )
        .order_by(HfObservation.observed_at)
    )  # fmt: skip
    out = RoundingCheck()
    seen: set[tuple[str, datetime]] = set()
    for sid, obs, hf_c, m_c in session.execute(q):
        if hf_c is None or m_c is None:  # filtered in SQL; keeps the types honest
            continue
        key = (sid, as_utc(obs))
        if key in seen:  # a COR and its original: one pair
            continue
        seen.add(key)
        out.pairs += 1
        f = temp_value(Decimal(m_c), "tenths_c", "metar_tgroup", as_utc(obs)).f_rounded
        expected = f_to_c(f)
        if Decimal(hf_c) == expected:
            out.matches += 1
        else:
            out.mismatches.append({
                "station": sid, "observed_at": as_utc(obs).isoformat(),
                "hf_c": int(hf_c), "metar_c": str(m_c), "station_f": f, "expected_c": expected,
            })  # fmt: skip
    return out


# ---------------------------------------------------------------- 5-minute high/low so far (B6)


class HfRowLike(Protocol):
    @property
    def observed_at(self) -> datetime: ...
    @property
    def temp_c(self) -> Decimal | None: ...
    @property
    def temp_precision(self) -> str | None: ...
    @property
    def qc(self) -> Any: ...


def qc_failed(qc: Any, var: str = "temperature") -> bool:
    dd = ((qc or {}).get(var) or {}).get("dd")
    return dd in QC_FAILED


@dataclass(frozen=True)
class HfExtreme:
    value_c: Decimal
    precision: str  # whole_c | tenths_c
    observed_at: datetime


@dataclass(frozen=True)
class HfDaySummary:
    high: HfExtreme | None
    low: HfExtreme | None
    readings: int  # 5-minute rows inside the day
    used: int  # rows that counted toward high/low
    excluded_qc_count: int
    excluded_off_grid_count: int
    missing_temp_count: int
    last_observed_at: datetime | None


def hf_day_summary(rows: Iterable[HfRowLike], start: datetime, end: datetime) -> HfDaySummary:
    """High and low of the 5-minute temperatures inside [start, end). QC-failed and off-grid
    values are left out and counted; missing values are counted; ties keep the earliest."""
    readings = used = bad_qc = off = missing = 0
    hi: HfExtreme | None = None
    lo: HfExtreme | None = None
    last: datetime | None = None
    for r in sorted(rows, key=lambda x: as_utc(x.observed_at)):
        at = as_utc(r.observed_at)
        if not (start <= at < end):
            continue
        readings += 1
        last = at
        if r.temp_c is None:
            missing += 1
            continue
        if qc_failed(r.qc):
            bad_qc += 1
            continue
        if r.temp_precision not in ("whole_c", "tenths_c"):
            off += 1
            continue
        used += 1
        v = Decimal(r.temp_c)
        if hi is None or v > hi.value_c:
            hi = HfExtreme(v, r.temp_precision, at)
        if lo is None or v < lo.value_c:
            lo = HfExtreme(v, r.temp_precision, at)
    return HfDaySummary(hi, lo, readings, used, bad_qc, off, missing, last)


def hf_rows(
    session: Session, station_id: str, start: datetime, end: datetime
) -> list[HfObservation]:
    q = (
        select(HfObservation)
        .where(
            HfObservation.station_id == station_id,
            HfObservation.observed_at >= start,
            HfObservation.observed_at < end,
        )
        .order_by(HfObservation.observed_at)
    )
    return list(session.scalars(q))
