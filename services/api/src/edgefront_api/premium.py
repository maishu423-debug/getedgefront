"""Premium 5-minute data for the Next.js server (v2 Phase 9 B6/B7). Mounted under
/api/v1/internal/, so every route requires X-Internal-Token (edgefront_api.internal); responses
are `private, no-store` (main.cache_headers), never publicly cached.

- GET /api/v1/internal/stations/{id}/hf?hours=6|24   5-minute readings, oldest first
- GET /api/v1/internal/stations/{id}/hf-current      latest reading + 5-minute high/low so far,
                                                    next to the METAR values
- GET /api/v1/internal/map                           every station: latest, high/low, METAR
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from edgefront_api import schemas as s
from edgefront_api import services
from edgefront_core.climate import climate_date, climate_day_bounds, effective_reports
from edgefront_core.hf_store import SOURCE as HF_SOURCE
from edgefront_core.hf_store import (
    HfDaySummary,
    HfExtreme,
    hf_day_summary,
    qc_failed,
)
from edgefront_core.models import HfObservation, SourceHealth, Station
from edgefront_core.settings import Settings
from edgefront_core.timeutil import as_utc
from edgefront_core.units import temp_value

premium_router = APIRouter(prefix="/api/v1/internal")


def _session(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.sessionmaker()
    try:
        yield session
    finally:
        session.close()


def _now(request: Request) -> datetime:
    return cast(datetime, request.app.state.now())


def _cfg(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


SessionDep = Annotated[Session, Depends(_session)]
NowDep = Annotated[datetime, Depends(_now)]
CfgDep = Annotated[Settings, Depends(_cfg)]
StationId = Annotated[str, Path(pattern=r"^[A-Za-z][A-Za-z0-9]{3}$")]


def _station(session: SessionDep, station_id: StationId) -> Station:
    try:
        return services.get_station(session, station_id)
    except services.NotFoundError:
        raise HTTPException(404, f"Unknown station {station_id}") from None


StationDep = Annotated[Station, Depends(_station)]


# ---------------------------------------------------------------- mapping


def _f(v: Decimal | None) -> float | None:
    return None if v is None else float(v)


def _hf_temp(
    c: Decimal | None, precision: str | None, at: datetime, st: Station
) -> s.TempValueOut | None:
    if c is None or precision not in ("whole_c", "tenths_c"):
        return None  # off grid: shown as the raw °C only, never converted as if exact
    p = cast(Literal["whole_c", "tenths_c"], precision)
    return services._temp_out(temp_value(Decimal(c), p, "hfmetar", at, services._unit(st)))


def reading_out(r: HfObservation, st: Station, now: datetime) -> s.HfReadingOut:
    at = as_utc(r.observed_at)
    qc: dict[str, Any] = r.qc or {}
    return s.HfReadingOut(
        observed_at=at,
        age_minutes=max(0, int((now - at).total_seconds() // 60)),
        temp=_hf_temp(r.temp_c, r.temp_precision, at, st),
        temp_c=_f(r.temp_c),
        temp_precision=cast(Literal["whole_c", "tenths_c", "off_grid"] | None, r.temp_precision),
        dewpt_c=_f(r.dewpt_c),
        wind_dir_deg=r.wind_dir_deg,
        wind_kt=r.wind_kt,
        gust_kt=r.gust_kt,
        altim_inhg=_f(r.altim_inhg),
        vis_mi=_f(r.vis_mi),
        precip_in=_f(r.precip_in),
        qc_temp=(qc.get("temperature") or {}).get("dd"),
        qc_failed=qc_failed(qc),
        qc=qc or None,
        revision=r.revision or 0,
        raw_message=r.raw_message,
        sky=[s.SkyLayerOut(cover=x["cover"], base_ft=x.get("base_ft")) for x in (r.sky or [])]
        or None,
        pres_wx=r.pres_wx,
        received_at=as_utc(r.received_at) if r.received_at else None,
        ingested_at=as_utc(r.ingested_at),
    )


def _extreme(e: HfExtreme | None, st: Station) -> s.HfExtremeOut | None:
    if e is None:
        return None
    t = _hf_temp(e.value_c, e.precision, e.observed_at, st)
    if t is None:  # extremes only come from on-grid values
        return None
    return s.HfExtremeOut(
        value_c=float(e.value_c),
        precision=cast(Literal["whole_c", "tenths_c"], e.precision),
        observed_at=e.observed_at,
        temp=t,
    )


def so_far_out(d: HfDaySummary, st: Station) -> s.HfSoFarOut:
    return s.HfSoFarOut(
        high=_extreme(d.high, st),
        low=_extreme(d.low, st),
        readings=d.readings,
        used=d.used,
        excluded_qc_count=d.excluded_qc_count,
        excluded_off_grid_count=d.excluded_off_grid_count,
        missing_temp_count=d.missing_temp_count,
    )


def _day(st: Station, now: datetime) -> tuple[datetime, datetime]:
    b = services.basis(st)
    return climate_day_bounds(climate_date(now, st.tz, b), st.tz, b)


def _source(session: Session) -> s.HfSourceRef:
    h = session.get(SourceHealth, HF_SOURCE)
    return s.HfSourceRef(
        last_success_at=as_utc(h.last_success_at) if h and h.last_success_at else None
    )


def _status(latest: HfObservation | None, now: datetime, stale_min: int) -> s.DataStatus:
    if latest is None:
        return "no_data"
    return "stale" if now - as_utc(latest.observed_at) > timedelta(minutes=stale_min) else "ok"


def _in_feed(session: Session, station_ids: list[str]) -> set[str]:
    """Stations with any 5-minute reading kept (7 days). KNYC and KBKF are not in the feed."""
    q = select(HfObservation.station_id).where(HfObservation.station_id.in_(station_ids)).distinct()
    return set(session.scalars(q))


def _metar_side(reps: list[services.RV], st: Station, now: datetime) -> s.MetarSideOut:
    eff = effective_reports(reps)
    latest = eff[-1] if eff else None
    return s.MetarSideOut(
        latest=services.metar_brief(latest, now, services._unit(st)) if latest else None,
        high_so_far=services._high_out(eff, st, now),
        low_so_far=services._low_out(eff, st, now),
    )


# ---------------------------------------------------------------- routes


@premium_router.get("/stations/{station_id}/hf", response_model=s.HfSeriesResponse)
def hf_series(
    session: SessionDep,
    st: StationDep,
    now: NowDep,
    cfg: CfgDep,
    hours: Annotated[int, Query(description="6 or 24")] = 6,
) -> s.HfSeriesResponse:
    if hours not in (6, 24):
        raise HTTPException(422, "hours must be 6 or 24")
    rows = session.scalars(
        select(HfObservation)
        .where(
            HfObservation.station_id == st.id,
            HfObservation.observed_at >= now - timedelta(hours=hours),
            HfObservation.observed_at <= now,
        )
        .order_by(HfObservation.observed_at)
    ).all()
    return s.HfSeriesResponse(
        generated_at=now,
        station_id=st.id,
        hours=hours,
        stale_after_minutes=cfg.hf_station_stale_minutes,
        in_feed=bool(rows) or st.id in _in_feed(session, [st.id]),
        source=_source(session),
        readings=[reading_out(r, st, now) for r in rows],
    )


@premium_router.get("/stations/{station_id}/hf-current", response_model=s.HfCurrentResponse)
def hf_current(
    session: SessionDep, st: StationDep, now: NowDep, cfg: CfgDep
) -> s.HfCurrentResponse:
    start, end = _day(st, now)
    rows = session.scalars(
        select(HfObservation)
        .where(
            HfObservation.station_id == st.id,
            HfObservation.observed_at >= min(start, now - timedelta(hours=2)),
            HfObservation.observed_at <= now,
        )
        .order_by(HfObservation.observed_at)
    ).all()
    latest = rows[-1] if rows else None
    reps = services._reports(session, [st.id], now - timedelta(hours=30))
    return s.HfCurrentResponse(
        generated_at=now,
        station_id=st.id,
        status=_status(latest, now, cfg.hf_station_stale_minutes),
        stale_after_minutes=cfg.hf_station_stale_minutes,
        in_feed=latest is not None or st.id in _in_feed(session, [st.id]),
        source=_source(session),
        latest=reading_out(latest, st, now) if latest else None,
        so_far=so_far_out(hf_day_summary(rows, start, end), st),
        metar=_metar_side(reps, st, now),
        climate_day=services.climate_day_out(st, now),
    )


@premium_router.get("/map", response_model=s.MapResponse)
def hf_map(session: SessionDep, now: NowDep, cfg: CfgDep) -> s.MapResponse:
    stations = list(session.scalars(select(Station).where(Station.active).order_by(Station.id)))
    ids = [st.id for st in stations]
    days = {st.id: _day(st, now) for st in stations}
    since = min([d[0] for d in days.values()] + [now - timedelta(hours=2)])
    hf: dict[str, list[HfObservation]] = defaultdict(list)
    for r in session.scalars(
        select(HfObservation)
        .where(HfObservation.station_id.in_(ids), HfObservation.observed_at >= since,
               HfObservation.observed_at <= now)
        .order_by(HfObservation.observed_at)
    ):  # fmt: skip
        hf[r.station_id].append(r)
    metar: dict[str, list[services.RV]] = defaultdict(list)
    for rv in services._reports(session, ids, now - timedelta(hours=30)):
        metar[rv.row.station_id].append(rv)
    feed = _in_feed(session, ids)
    venues = services._venues_by_station(session)
    order = {"kalshi": 0, "polymarket": 1, "robinhood": 2}
    out: list[s.MapStationOut] = []
    for st in stations:
        rows = hf.get(st.id, [])
        latest = rows[-1] if rows else None
        start, end = days[st.id]
        out.append(
            s.MapStationOut(
                station_id=st.id,
                name=st.name,
                city=st.city,
                state=st.state,
                tz=st.tz,
                lat=st.lat,
                lon=st.lon,
                venues=sorted({v.venue for v in venues.get(st.id, [])}, key=lambda v: order[v]),
                status=_status(latest, now, cfg.hf_station_stale_minutes),
                in_feed=st.id in feed,
                hf_latest=reading_out(latest, st, now) if latest else None,
                hf_so_far=so_far_out(hf_day_summary(rows, start, end), st),
                metar=_metar_side(metar.get(st.id, []), st, now),
            )
        )
    return s.MapResponse(generated_at=now, source=_source(session), stations=out)
