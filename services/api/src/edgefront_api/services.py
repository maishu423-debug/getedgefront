"""Read-side assembly for the API. Reads Postgres only; never contacts upstream."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Literal, cast
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from edgefront_api import daily
from edgefront_api import schemas as s
from edgefront_core.climate import (
    DayBasis,
    climate_date,
    climate_day_bounds,
    effective_reports,
    high_so_far,
    low_so_far,
    standard_offset,
)
from edgefront_core.hf_store import SOURCE as HF_SOURCE
from edgefront_core.hf_store import (
    StageStats,
    latency_report,
    rounding_check,
    stations_reporting,
)
from edgefront_core.metar_ingest import SOURCE as METAR_SOURCE
from edgefront_core.metar_ingest import SOURCE_LABEL as METAR_LABEL
from edgefront_core.models import (
    DailyHighEvent,
    HfFile,
    HfObservation,
    MetarReport,
    SourceHealth,
    Station,
    StationVenue,
)
from edgefront_core.settings import Settings
from edgefront_core.sources import known_sources
from edgefront_core.units import (
    NativeUnit,
    TempValue,
    c_to_f_display,
    compass_point,
    metar_temp_value,
    rh_percent,
)

GAP_MINUTES = 90
FRESH_HIGH_MINUTES = 60
COVER_RANK = {"CLR": 0, "SKC": 0, "FEW": 1, "SCT": 2, "BKN": 3, "OVC": 4, "VV": 5}
ZONE_GROUPS = {-300: "Eastern", -360: "Central", -420: "Mountain", -480: "Pacific"}


class NotFoundError(LookupError):
    pass


def utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _num(v: Decimal | None, places: int = 1) -> float | None:
    return None if v is None else round(float(v), places)


# ---------------------------------------------------------------- stations


def basis(st: Station) -> DayBasis:
    return "LOCAL" if st.day_basis == "LOCAL" else "LST"


def std_offset_minutes(st: Station, now: datetime) -> int:
    return int(standard_offset(ZoneInfo(st.tz), now).total_seconds() // 60)


def zone_group(offset_min: int) -> str:
    if offset_min in ZONE_GROUPS:
        return ZONE_GROUPS[offset_min]
    h, m = divmod(abs(offset_min), 60)
    return f"UTC{'-' if offset_min < 0 else '+'}{h}" + (f":{m:02d}" if m else "")


def climate_day_out(st: Station, now: datetime) -> s.ClimateDayOut:
    b = basis(st)
    day = climate_date(now, st.tz, b)
    start, end = climate_day_bounds(day, st.tz, b)
    total = (end - start).total_seconds()
    return s.ClimateDayOut(
        date=day,
        basis=b,
        start=start,
        end=end,
        ends_in_minutes=max(0, int((end - now).total_seconds() // 60)),
        elapsed_fraction=round(min(1.0, max(0.0, (now - start).total_seconds() / total)), 4),
    )


def _venue(v: StationVenue) -> s.VenueOut:
    return s.VenueOut(
        venue=v.venue.value,
        kind=v.market_kind.value,
        market=v.market,
        settlement_source=v.settlement_source,
        rules_url=v.rules_url,
        verified=v.verified,
        verified_at=utc(v.verified_at) if v.verified_at else None,
    )


def _venues_by_station(session: Session) -> dict[str, list[s.VenueOut]]:
    out: dict[str, list[s.VenueOut]] = defaultdict(list)
    rows = session.scalars(
        select(StationVenue).order_by(StationVenue.venue, StationVenue.market_kind)
    )
    for v in rows:
        out[v.station_id].append(_venue(v))
    return out


def get_station(session: Session, station_id: str) -> Station:
    st = session.get(Station, station_id.upper())
    if st is None or not st.active:
        raise NotFoundError(station_id)
    return st


def station_meta(session: Session, st: Station, now: datetime) -> s.StationMeta:
    venues = _venues_by_station(session).get(st.id, [])
    off = std_offset_minutes(st, now)
    return s.StationMeta(
        id=st.id,
        name=st.name,
        aliases=list(st.aliases or []),
        official_name=st.official_name,
        city=st.city,
        state=st.state,
        lat=st.lat,
        lon=st.lon,
        elevation_m=st.elevation_m,
        tz=st.tz,
        std_utc_offset_minutes=off,
        zone_group=zone_group(off),
        local_time=now.astimezone(ZoneInfo(st.tz)),
        nws_office=st.nws_office,
        grid_x=st.grid_x,
        grid_y=st.grid_y,
        dsm_location=st.dsm_location,
        pfm_point=st.pfm_point,
        venues=venues,
        venues_verified=bool(venues) and all(v.verified for v in venues),
    )


# ---------------------------------------------------------------- METAR views


@dataclass(frozen=True)
class RV:
    """Tz-aware read-only view of a stored report."""

    row: MetarReport
    id: int
    observed_at: datetime
    report_type: str
    is_correction: bool
    temp_c: Decimal | None
    temp_precision: str | None
    max6h_c: Decimal | None
    min6h_c: Decimal | None

    @classmethod
    def of(cls, r: MetarReport) -> RV:
        return cls(
            r,
            r.id,
            utc(r.observed_at),
            r.report_type,
            r.is_correction,
            r.temp_c,
            r.temp_precision,
            r.max6h_c,
            r.min6h_c,
        )


def _reports(session: Session, station_ids: Iterable[str], since: datetime) -> list[RV]:
    rows = session.scalars(
        select(MetarReport)
        .where(MetarReport.station_id.in_(list(station_ids)), MetarReport.observed_at >= since)
        .order_by(MetarReport.observed_at, MetarReport.id)
    )
    return [RV.of(r) for r in rows]


def _age(now: datetime, t: datetime) -> int:
    return max(0, int((now - t).total_seconds() // 60))


def _precision(p: str | None) -> Literal["tenths", "whole"] | None:
    return cast(Literal["tenths", "whole"] | None, p)


def _rtype(t: str) -> Literal["METAR", "SPECI"]:
    return "SPECI" if t == "SPECI" else "METAR"


def _unit(st: Station) -> NativeUnit:
    return "C" if st.native_temp_unit == "C" else "F"


def metar_brief(r: RV, now: datetime, native: NativeUnit = "F") -> s.MetarBrief:
    return s.MetarBrief(
        report_id=r.id,
        report_type=_rtype(r.report_type),
        observed_at=r.observed_at,
        age_minutes=_age(now, r.observed_at),
        temp_c=_num(r.temp_c),
        temp_f=c_to_f_display(r.temp_c),
        temp_precision=_precision(r.temp_precision),
        temp=_temp_out(
            metar_temp_value(r.temp_c, r.temp_precision, r.observed_at, native_unit=native)
        )
        if r.temp_c is not None
        else None,
    )


def _temp_out(t: TempValue) -> s.TempValueOut:
    return s.TempValueOut(
        c=float(t.c),
        f_exact=float(t.f_exact),
        f_rounded=t.f_rounded,
        f_possible=list(t.f_possible) if t.f_possible is not None else None,
        precision=t.precision,
        source=t.source,
        observed_at=t.observed_at,
    )


def _sky(r: MetarReport) -> list[s.SkyLayerOut]:
    return [s.SkyLayerOut.model_validate(layer) for layer in (r.sky or [])]


def metar_out(
    r: RV, now: datetime, superseded: bool = False, native: NativeUnit = "F"
) -> s.MetarOut:
    m = r.row
    return s.MetarOut(
        **metar_brief(r, now, native).model_dump(),
        raw_text=m.raw_text,
        is_correction=m.is_correction,
        superseded=superseded,
        fetched_at=utc(m.fetched_at),
        dewpt_c=_num(m.dewpt_c),
        dewpt_f=c_to_f_display(m.dewpt_c),
        rh_computed=rh_percent(m.temp_c, m.dewpt_c),
        wind_dir_deg=m.wind_dir_deg,
        wind_compass=compass_point(m.wind_dir_deg),
        wind_vrb=m.wind_vrb,
        wind_kt=m.wind_kt,
        gust_kt=m.gust_kt,
        vis_mi=_num(m.vis_mi, 2),
        sky=_sky(m),
        altim_inhg=_num(m.altim_inhg, 2),
        slp_hpa=_num(m.slp_hpa),
        max6h_c=_num(m.max6h_c),
        min6h_c=_num(m.min6h_c),
        max24h_c=_num(m.max24h_c),
        min24h_c=_num(m.min24h_c),
    )


def _high_out(reports: list[RV], st: Station, now: datetime) -> s.HighSoFarOut | None:
    b = basis(st)
    start, end = climate_day_bounds(climate_date(now, st.tz, b), st.tz, b)
    h = high_so_far(reports, start, end)
    if h is None:
        return None
    src = next(r for r in reports if r.id == h.report_id)
    return s.HighSoFarOut(
        value_c=float(h.value_c),
        value_f=c_to_f_display(h.value_c),
        precision=_precision(h.precision),
        kind="max6h" if h.kind == "max6h" else "report",
        report_id=h.report_id,
        report_type=_rtype(src.report_type),
        observed_at=h.observed_at,
        temp=_temp_out(
            metar_temp_value(
                h.value_c,
                h.precision,
                h.observed_at,
                six_hour=h.kind == "max6h",
                native_unit=_unit(st),
            )
        ),
    )


def _low_out(reports: list[RV], st: Station, now: datetime) -> s.LowSoFarOut | None:
    b = basis(st)
    start, end = climate_day_bounds(climate_date(now, st.tz, b), st.tz, b)
    lo = low_so_far(reports, start, end)
    if lo is None:
        return None
    src = next(r for r in reports if r.id == lo.report_id)
    return s.LowSoFarOut(
        value_c=float(lo.value_c),
        value_f=c_to_f_display(lo.value_c),
        precision=_precision(lo.precision),
        kind="min6h" if lo.kind == "min6h" else "report",
        report_id=lo.report_id,
        report_type=_rtype(src.report_type),
        observed_at=lo.observed_at,
        temp=_temp_out(
            metar_temp_value(
                lo.value_c,
                lo.precision,
                lo.observed_at,
                six_hour=lo.kind == "min6h",
                native_unit=_unit(st),
            )
        ),
    )


def _metar_source(session: Session) -> s.SourceRef:
    h = session.get(SourceHealth, METAR_SOURCE)
    return s.SourceRef(
        source=METAR_LABEL,
        producer="NOAA Aviation Weather Center",
        last_success_at=utc(h.last_success_at) if h and h.last_success_at else None,
    )


def _status(latest: RV | None, now: datetime, stale_min: int) -> s.DataStatus:
    if latest is None:
        return "no_data"
    return "stale" if _age(now, latest.observed_at) > stale_min else "ok"


# ---------------------------------------------------------------- endpoints


def board(
    session: Session, now: datetime, settings: Settings, venue: str | None
) -> s.StationsResponse:
    stations = list(session.scalars(select(Station).where(Station.active).order_by(Station.id)))
    venues = _venues_by_station(session)
    if venue:
        stations = [st for st in stations if any(v.venue == venue for v in venues.get(st.id, []))]
    since = now - timedelta(hours=30)  # covers any station's current climate day (+ 6 h groups)
    by_station: dict[str, list[RV]] = defaultdict(list)
    for r in _reports(session, [st.id for st in stations], since):
        by_station[r.row.station_id].append(r)
    fresh_cutoff = now - timedelta(minutes=FRESH_HIGH_MINUTES)
    fresh = {
        sid
        for (sid,) in session.execute(
            select(DailyHighEvent.station_id).where(DailyHighEvent.observed_at >= fresh_cutoff)
        )
    }
    rows: list[s.BoardRow] = []
    any_data = False
    for st in stations:
        reps = effective_reports(by_station.get(st.id, []))
        latest = reps[-1] if reps else None
        any_data = any_data or latest is not None
        off = std_offset_minutes(st, now)
        cday = climate_day_out(st, now)
        rows.append(
            s.BoardRow(
                id=st.id,
                name=st.name,
                aliases=list(st.aliases or []),
                city=st.city,
                state=st.state,
                tz=st.tz,
                zone_group=zone_group(off),
                std_utc_offset_minutes=off,
                local_time=now.astimezone(ZoneInfo(st.tz)),
                venues=venues.get(st.id, []),
                latest=metar_brief(latest, now, _unit(st)) if latest else None,
                high_so_far=_high_out(reps, st, now),
                low_so_far=_low_out(reps, st, now),
                nws_today_high_f=daily.today_high_f(daily.latest_forecast(session, st.id), st, now),
                is_stale=latest is None
                or _age(now, latest.observed_at) > settings.stale_metar_minutes,
                fresh_high=st.id in fresh,
                climate_day=cday,
            )
        )
    return s.StationsResponse(
        generated_at=now,
        status="ok" if any_data else "no_data",
        source=_metar_source(session),
        stale_after_minutes=settings.stale_metar_minutes,
        stations=rows,
    )


def current(session: Session, st: Station, now: datetime, settings: Settings) -> s.CurrentResponse:
    reps = effective_reports(_reports(session, [st.id], now - timedelta(hours=30)))
    latest = reps[-1] if reps else None
    status = _status(latest, now, settings.stale_metar_minutes)
    return s.CurrentResponse(
        generated_at=now,
        station_id=st.id,
        status=status,
        source=_metar_source(session),
        stale_after_minutes=settings.stale_metar_minutes,
        is_stale=status != "ok",
        latest=metar_out(latest, now, native=_unit(st)) if latest else None,
        high_so_far=_high_out(reps, st, now),
        low_so_far=_low_out(reps, st, now),
        climate_day=climate_day_out(st, now),
    )


def metars(
    session: Session, st: Station, now: datetime, settings: Settings, hours: int
) -> s.MetarsResponse:
    allr = _reports(session, [st.id], now - timedelta(hours=hours))
    eff = {r.id for r in effective_reports(allr)}
    newest_first = sorted(allr, key=lambda r: (r.observed_at, r.id), reverse=True)
    latest = max((r for r in allr if r.id in eff), key=lambda r: r.observed_at, default=None)
    return s.MetarsResponse(
        generated_at=now,
        station_id=st.id,
        status=_status(latest, now, settings.stale_metar_minutes),
        hours=hours,
        source=_metar_source(session),
        reports=[
            metar_out(r, now, superseded=r.id not in eff, native=_unit(st)) for r in newest_first
        ],
    )


def _sky_cover(layers: list[s.SkyLayerOut]) -> str | None:
    if not layers:
        return None
    return max(layers, key=lambda layer: COVER_RANK.get(layer.cover, -1)).cover


def observed(
    session: Session, st: Station, now: datetime, settings: Settings, hours: int
) -> s.ObservedResponse:
    reps = effective_reports(_reports(session, [st.id], now - timedelta(hours=hours)))
    points: list[s.ObservedPoint] = []
    for r in reps:
        m = r.row
        sky = _sky(m)
        points.append(
            s.ObservedPoint(
                report_id=r.id,
                report_type=_rtype(r.report_type),
                observed_at=r.observed_at,
                temp_c=_num(m.temp_c),
                temp_f=c_to_f_display(m.temp_c),
                dewpt_c=_num(m.dewpt_c),
                dewpt_f=c_to_f_display(m.dewpt_c),
                rh_computed=rh_percent(m.temp_c, m.dewpt_c),
                wind_dir_deg=m.wind_dir_deg,
                wind_vrb=m.wind_vrb,
                wind_kt=m.wind_kt,
                gust_kt=m.gust_kt,
                altim_inhg=_num(m.altim_inhg, 2),
                sky_cover=_sky_cover(sky),
                sky=sky,
            )
        )
    gaps: list[s.Gap] = []
    window_start = now - timedelta(hours=hours)
    edges = [window_start, *[p.observed_at for p in points], now]
    for a, b in pairwise(edges):
        mins = int((b - a).total_seconds() // 60)
        if mins > GAP_MINUTES:
            gaps.append(s.Gap(start=a, end=b, minutes=mins))
    return s.ObservedResponse(
        generated_at=now,
        station_id=st.id,
        status=_status(reps[-1] if reps else None, now, settings.stale_metar_minutes),
        hours=hours,
        source=_metar_source(session),
        gap_minutes=GAP_MINUTES,
        points=points,
        gaps=gaps,
    )


def new_highs(session: Session, now: datetime, limit: int) -> s.FeedResponse:
    rows = session.execute(
        select(DailyHighEvent, Station, MetarReport.report_type)
        .join(Station, Station.id == DailyHighEvent.station_id)
        .join(MetarReport, MetarReport.id == DailyHighEvent.report_id)
        .where(Station.active)
        .order_by(DailyHighEvent.observed_at.desc(), DailyHighEvent.id.desc())
        .limit(limit)
    ).all()
    events = []
    for ev, st, rtype in rows:
        events.append(
            s.HighEventOut(
                station_id=st.id,
                station_name=st.name,
                city=st.city,
                climate_date=ev.climate_date,
                from_c=float(ev.from_c),
                from_f=c_to_f_display(ev.from_c),
                to_c=float(ev.to_c),
                to_f=c_to_f_display(ev.to_c),
                observed_at=utc(ev.observed_at),
                report_id=ev.report_id,
                report_type=_rtype(rtype),
            )
        )
    return s.FeedResponse(generated_at=now, source=_metar_source(session), events=events)


def status(session: Session, now: datetime, settings: Settings) -> s.StatusResponse:
    out = []
    for src in known_sources(settings):
        h = session.get(SourceHealth, src.key)
        last_ok = utc(h.last_success_at) if h and h.last_success_at else None
        out.append(
            s.SourceStatus(
                key=src.key,
                label=src.label,
                producer=src.producer,
                schedule_seconds=src.schedule_seconds,
                last_success_at=last_ok,
                last_attempt_at=utc(h.last_attempt_at) if h and h.last_attempt_at else None,
                last_error_at=utc(h.last_error_at) if h and h.last_error_at else None,
                last_item_time=utc(h.last_item_time) if h and h.last_item_time else None,
                healthy=last_ok is not None
                and (now - last_ok).total_seconds() <= src.unhealthy_after_seconds,
            )
        )
    return s.StatusResponse(generated_at=now, sources=out, hfmetar=hf_status(session, now))


def _stage(v: StageStats) -> s.HfStageOut:
    return s.HfStageOut(count=v.count, p50_s=v.p50_s, p95_s=v.p95_s)


def hf_status(session: Session, now: datetime) -> s.HfStatusOut:
    """v2 Phase 9 B8: the 5-minute pipeline on /status (a block of its own, not in `sources`)."""
    h = session.get(SourceHealth, HF_SOURCE)
    f = session.scalars(select(HfFile).order_by(HfFile.processed_at.desc()).limit(1)).first()
    last = session.scalar(select(func.max(HfObservation.observed_at)))
    active = list(session.scalars(select(Station.id).where(Station.active).order_by(Station.id)))
    reporting = [sid for sid in stations_reporting(session, now, 30) if sid in set(active)]
    lat = latency_report(session, now, hours=6)
    rc = rounding_check(session, now - timedelta(days=7))
    return s.HfStatusOut(
        last_success_at=utc(h.last_success_at) if h and h.last_success_at else None,
        last_error_at=utc(h.last_error_at) if h and h.last_error_at else None,
        last_file=s.HfFileOut(
            name=f.name,
            modified_at=utc(f.modified_at),
            processed_at=utc(f.processed_at),
            our_rows=f.our_rows,
        )
        if f
        else None,
        last_reading_at=utc(last) if last else None,
        stations_reporting_30m=reporting,
        stations_missing_30m=[sid for sid in active if sid not in set(reporting)],
        latency=s.HfLatencyOut(
            window_hours=lat.window_hours,
            rows=lat.rows,
            excluded_late=lat.excluded_late,
            **{k: _stage(v) for k, v in lat.overall.items()},
            per_station={
                sid: {k: _stage(v) for k, v in st.items()} for sid, st in lat.per_station.items()
            },
        ),
        rounding_check=s.HfRoundingCheckOut(
            pairs=rc.pairs,
            matches=rc.matches,
            mismatches=len(rc.mismatches),
            mismatch_examples=[f"{m['station']} {m['observed_at']}" for m in rc.mismatches[:5]],
        ),
    )
