"""Climate day, "high so far" and new-high events (CONTEXT.md §6.2, §6.3).

- Climate day (basis LST): midnight to midnight local *standard* time, as NWS DSM/CLI use.
  During DST that is 1:00 AM to 1:00 AM on the local clock. Basis LOCAL: calendar day on the
  local clock (23 or 25 h on DST change days). Days are half-open: [start, end).
- High so far: max of (a) temperatures of every effective METAR/SPECI observed inside the day,
  and (b) 6-hour max groups whose 6-hour window lies entirely inside the day (a window ending
  exactly at `end` counts, Q12). Ties keep the earliest report.
- Corrections: a COR replaces the report it corrects (same station, time and type).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from edgefront_core.parsers.metar import synoptic_hour

DayBasis = Literal["LST", "LOCAL"]
SIX_HOURS = timedelta(hours=6)


# ---------------------------------------------------------------- climate day


def standard_offset(tz: ZoneInfo, at: datetime) -> timedelta:
    """UTC offset of local *standard* time at instant `at` (DST removed)."""
    local = at.astimezone(tz)
    off = local.utcoffset() or timedelta(0)
    return off - (local.dst() or timedelta(0))


def climate_date(at: datetime, tz_name: str, basis: DayBasis = "LST") -> date:
    tz = ZoneInfo(tz_name)
    if basis == "LOCAL":
        return at.astimezone(tz).date()
    return (at + standard_offset(tz, at)).replace(tzinfo=None).date()


def climate_day_bounds(
    day: date, tz_name: str, basis: DayBasis = "LST"
) -> tuple[datetime, datetime]:
    """UTC [start, end) of a climate day."""
    tz = ZoneInfo(tz_name)
    if basis == "LOCAL":
        start = datetime.combine(day, time(0), tzinfo=tz)
        end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=tz)
        return start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))
    noon = datetime.combine(day, time(12), tzinfo=tz)
    off = standard_offset(tz, noon)
    start = datetime.combine(day, time(0), tzinfo=ZoneInfo("UTC")) - off
    return start, start + timedelta(days=1)


# ---------------------------------------------------------------- reports


class ReportLike(Protocol):
    @property
    def id(self) -> int: ...
    @property
    def observed_at(self) -> datetime: ...
    @property
    def report_type(self) -> str: ...
    @property
    def is_correction(self) -> bool: ...
    @property
    def temp_c(self) -> Decimal | None: ...
    @property
    def temp_precision(self) -> str | None: ...
    @property
    def max6h_c(self) -> Decimal | None: ...


def effective_reports[R: ReportLike](reports: Iterable[R]) -> list[R]:
    """One report per (observed_at, report_type): the latest correction if any, otherwise the
    latest original. Sorted by observed_at, then id."""
    best: dict[tuple[datetime, str], R] = {}
    for r in reports:
        key = (r.observed_at, r.report_type)
        cur = best.get(key)
        if cur is None or (r.is_correction, r.id) > (cur.is_correction, cur.id):
            best[key] = r
    return sorted(best.values(), key=lambda r: (r.observed_at, r.id))


@dataclass(frozen=True)
class Candidate:
    value_c: Decimal
    kind: Literal["report", "max6h"]
    precision: str | None
    report_id: int
    observed_at: datetime  # time of the report the value came from


def six_hour_window(observed_at: datetime) -> tuple[datetime, datetime] | None:
    end = synoptic_hour(observed_at)
    return None if end is None else (end - SIX_HOURS, end)


def candidates(r: ReportLike, start: datetime, end: datetime) -> list[Candidate]:
    out: list[Candidate] = []
    if start <= r.observed_at < end and r.temp_c is not None:
        out.append(Candidate(Decimal(r.temp_c), "report", r.temp_precision, r.id, r.observed_at))
    if r.max6h_c is not None:
        win = six_hour_window(r.observed_at)
        if win is not None and win[0] >= start and win[1] <= end:
            out.append(Candidate(Decimal(r.max6h_c), "max6h", "tenths", r.id, r.observed_at))
    return out


def _best(cands: Sequence[Candidate]) -> Candidate | None:
    # Highest value; on a tie the earliest report (then a plain reading over a 6 h group).
    if not cands:
        return None
    return min(cands, key=lambda c: (-c.value_c, c.observed_at, c.kind != "report"))


def high_so_far(reports: Iterable[ReportLike], start: datetime, end: datetime) -> Candidate | None:
    cands = [c for r in effective_reports(reports) for c in candidates(r, start, end)]
    return _best(cands)


@dataclass(frozen=True)
class HighEvent:
    from_c: Decimal
    to_c: Decimal
    report_id: int
    observed_at: datetime


def high_events(reports: Iterable[ReportLike], start: datetime, end: datetime) -> list[HighEvent]:
    """Each time a report raises the day's high so far. The first report that sets a high is
    the baseline, not an event (§6.3)."""
    events: list[HighEvent] = []
    running: Decimal | None = None
    for r in effective_reports(reports):
        best = _best(candidates(r, start, end))
        if best is None:
            continue
        if running is None:
            running = best.value_c
        elif best.value_c > running:
            events.append(HighEvent(running, best.value_c, r.id, r.observed_at))
            running = best.value_c
    return events
