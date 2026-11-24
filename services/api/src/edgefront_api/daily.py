"""Daily summaries (CLI + DSM) and NWS forecast views. Reads Postgres only."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from edgefront_api import schemas as s
from edgefront_core.climate import climate_date
from edgefront_core.models import CliProduct, DsmProduct, NwsForecast, SourceHealth, Station
from edgefront_core.parsers.forecast import (
    Period,
    hourly_strip,
    parse_periods,
    today_period,
    tonight_period,
)
from edgefront_core.settings import Settings

IEM_ATTRIBUTION = "DSM via Iowa Environmental Mesonet, Iowa State University"
CLI_NAME = "Daily Climate Report"
DSM_NAME = "ASOS Daily Summary"
NONE_MESSAGE = "No daily summary available for this station"


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _health(session: Session, key: str) -> datetime | None:
    h = session.get(SourceHealth, key)
    return _utc(h.last_success_at) if h else None


def _pick[T: (CliProduct, DsmProduct)](rows: list[T]) -> T | None:
    """Latest final (a later correction or re-issue wins), else the latest intraday."""
    finals = [r for r in rows if r.report_kind == "final"]
    pool = finals or rows
    return max(pool, key=lambda r: (_utc(r.issued_at), r.id)) if pool else None


def _errors(v: Any) -> list[str]:
    return [str(e) for e in v] if isinstance(v, list) else []


def _cli_row(
    st: Station, day: date, which: Literal["today", "yesterday"], rows: list[CliProduct]
) -> s.DailySummaryRow:
    base: dict[str, Any] = {
        "product": "CLI", "product_name": CLI_NAME, "day": which,
        "issuances_for_day": len(rows),
    }  # fmt: skip
    if st.cli_location is None:
        return s.DailySummaryRow(
            **base,
            status="not_available",
            reason="Not published for this station",
            covers=s.CoversOut(date=day, kind=None),
        )
    r = _pick(rows)
    if r is None:
        reason = (
            "No CLI for today yet. When the office issues an intraday update, it appears here "
            "with its 'valid as of' time."
            if which == "today"
            else "Yesterday's CLI has not been received yet. The final report is usually issued "
            "shortly after local midnight."
        )
        return s.DailySummaryRow(
            **base,
            status="not_issued_yet",
            reason=reason,
            covers=s.CoversOut(date=day, kind="preliminary" if which == "today" else "final"),
            source="nws_api",
        )
    kind = cast(Literal["preliminary", "final"] | None, r.report_kind)
    return s.DailySummaryRow(
        **base,
        status="ok",
        covers=s.CoversOut(date=day, kind=kind),
        issuer=r.issuer,
        source="nws_api",
        source_label="api.weather.gov",
        product_id=r.product_id,
        issued_at=_utc(r.issued_at),
        valid_as_of_local=r.valid_as_of_local,
        is_correction=r.is_correction,
        max_f=r.max_temp_f,
        max_time_local=r.max_time_local,
        min_f=r.min_temp_f,
        min_time_local=r.min_time_local,
        precip_in=float(r.precip_in) if r.precip_in is not None else None,
        precip_trace=r.precip_trace,
        normal_high_f=r.normal_high_f,
        normal_low_f=r.normal_low_f,
        departure_high_f=r.departure_high_f,
        departure_low_f=r.departure_low_f,
        raw_text=r.raw_text,
        decode_errors=_errors(r.decode_errors),
    )


def _dsm_row(
    st: Station, day: date, which: Literal["today", "yesterday"], rows: list[DsmProduct]
) -> s.DailySummaryRow:
    base: dict[str, Any] = {
        "product": "DSM", "product_name": DSM_NAME, "day": which,
        "issuances_for_day": len(rows),
    }  # fmt: skip
    if st.dsm_source is None:
        return s.DailySummaryRow(
            **base,
            status="not_available",
            reason="Not published for this station",
            covers=s.CoversOut(date=day, kind=None),
        )
    src = cast(Literal["nws_api", "iem"], st.dsm_source)
    r = _pick(rows)
    if r is None:
        reason = (
            "No DSM for today yet. This station's ASOS issues its summaries at its own "
            "scheduled hours, so a morning without one is normal."
            if which == "today"
            else "Yesterday's final DSM has not been received yet. It is issued after local "
            "midnight."
        )
        return s.DailySummaryRow(
            **base,
            status="not_issued_yet",
            reason=reason,
            covers=s.CoversOut(date=day, kind="so_far" if which == "today" else "final"),
            source=src,
            attribution=IEM_ATTRIBUTION if src == "iem" else None,
        )
    kind = cast(Literal["so_far", "final"] | None, r.report_kind)
    issue_local = None if r.issue_key == "FINAL" else f"{r.issue_key[:2]}:{r.issue_key[2:]}"

    def wind(d: int | None, spd: int | None, t: str | None) -> s.WindOut | None:
        return None if spd is None else s.WindOut(dir_deg=d, speed_mph=spd, time_local=t)

    return s.DailySummaryRow(
        **base,
        status="ok",
        covers=s.CoversOut(date=day, kind=kind),
        issuer=r.issuer,
        source=cast(Literal["nws_api", "iem"], r.source),
        source_label="Iowa Environmental Mesonet (IEM)" if r.source == "iem" else "api.weather.gov",
        attribution=IEM_ATTRIBUTION if r.source == "iem" else None,
        product_id=r.product_id,
        issued_at=_utc(r.issued_at),
        valid_as_of_local=issue_local,
        is_correction=r.is_correction,
        max_f=r.max_temp_f,
        max_time_local=r.max_time_local,
        min_f=r.min_temp_f,
        min_time_local=r.min_time_local,
        precip_in=float(r.precip_in) if r.precip_in is not None else None,
        precip_trace=r.precip_trace,
        peak_wind=wind(r.peak_wind_dir, r.peak_wind_speed, r.peak_wind_time_local),
        peak_gust=wind(r.peak_gust_dir, r.peak_gust_speed, r.peak_gust_time_local),
        raw_text=r.raw_text,
        decode_errors=_errors(r.decode_errors),
    )


def daily_summaries(session: Session, st: Station, now: datetime) -> s.DailySummariesResponse:
    basis: Literal["LST", "LOCAL"] = "LOCAL" if st.day_basis == "LOCAL" else "LST"
    today = climate_date(now, st.tz, basis)
    yesterday = today - timedelta(days=1)
    clis = list(
        session.scalars(
            select(CliProduct).where(
                CliProduct.station_id == st.id, CliProduct.climate_date.in_([today, yesterday])
            )
        )
    )
    dsms = list(
        session.scalars(
            select(DsmProduct).where(
                DsmProduct.station_id == st.id, DsmProduct.climate_date.in_([today, yesterday])
            )
        )
    )
    rows = [
        _cli_row(st, today, "today", [r for r in clis if r.climate_date == today]),
        _dsm_row(st, today, "today", [r for r in dsms if r.climate_date == today]),
        _cli_row(st, yesterday, "yesterday", [r for r in clis if r.climate_date == yesterday]),
        _dsm_row(st, yesterday, "yesterday", [r for r in dsms if r.climate_date == yesterday]),
    ]
    none = st.cli_location is None and st.dsm_source is None
    sources = []
    if st.cli_location:
        sources.append(
            s.SourceRef(
                source="api.weather.gov/products (CLI)",
                producer="National Weather Service",
                last_success_at=_health(session, "cli"),
            )
        )
    if st.dsm_source == "iem":
        sources.append(
            s.SourceRef(
                source="mesonet.agron.iastate.edu AFOS archive (DSM)",
                producer=f"National Weather Service ASOS · {IEM_ATTRIBUTION}",
                last_success_at=_health(session, "dsm_iem"),
            )
        )
    elif st.dsm_source == "nws_api":
        sources.append(
            s.SourceRef(
                source="api.weather.gov/products (DSM)",
                producer="National Weather Service ASOS",
                last_success_at=_health(session, "dsm_nws"),
            )
        )
    return s.DailySummariesResponse(
        generated_at=now,
        station_id=st.id,
        tz=st.tz,
        status="none_available" if none else "ok",
        message=NONE_MESSAGE if none else None,
        today=today,
        yesterday=yesterday,
        rows=rows,
        sources=sources,
    )


# ---------------------------------------------------------------- forecast


def latest_forecast(session: Session, station_id: str) -> NwsForecast | None:
    return session.scalars(
        select(NwsForecast)
        .where(NwsForecast.station_id == station_id)
        .order_by(NwsForecast.fetched_at.desc(), NwsForecast.id.desc())
    ).first()


def _periods(raw: Any) -> list[Period]:
    if not isinstance(raw, list):
        return []
    return parse_periods({"properties": {"periods": raw}})


def today_high_f(row: NwsForecast | None, st: Station, now: datetime) -> int | None:
    if row is None:
        return None
    p = today_period(_periods(row.periods), now, st.tz)
    return p.temperature_f if p else None


def _period_out(p: Period | None) -> s.ForecastPeriodOut | None:
    if p is None:
        return None
    return s.ForecastPeriodOut(
        name=p.name,
        start=p.start,
        end=p.end,
        temperature_f=p.temperature_f,
        pop_percent=p.pop_percent,
        short=p.short,
        detailed=p.detailed,
    )


def forecast(session: Session, st: Station, now: datetime, cfg: Settings) -> s.ForecastResponse:
    row = latest_forecast(session, st.id)
    src = s.SourceRef(
        source="api.weather.gov/gridpoints",
        producer=f"National Weather Service{f' ({st.nws_office})' if st.nws_office else ''}",
        last_success_at=_health(session, "forecast"),
    )
    url = (
        f"https://forecast.weather.gov/MapClick.php?lat={st.lat:.4f}&lon={st.lon:.4f}"
        if st.lat is not None and st.lon is not None
        else None
    )
    if row is None:
        return s.ForecastResponse(
            generated_at=now, station_id=st.id, status="no_data", source=src,
            office=st.nws_office, update_time=None, fetched_at=None, today_high_f=None,
            tonight_low_f=None, today=None, tonight=None, hourly=[], weather_gov_url=url,
        )  # fmt: skip
    periods = _periods(row.periods)
    t, n = today_period(periods, now, st.tz), tonight_period(periods, now, st.tz)
    fetched = _utc(row.fetched_at)
    stale = fetched is None or (now - fetched) > timedelta(seconds=3 * cfg.forecast_poll_seconds)
    tz = ZoneInfo(st.tz)
    note = None
    if t is None and any(p.is_daytime for p in periods):
        note = (
            "Today's daytime forecast period has ended; tomorrow's high is not shown here."
            if now.astimezone(tz).hour >= 12
            else "No daytime forecast period for today in the latest NWS forecast."
        )
    return s.ForecastResponse(
        generated_at=now,
        station_id=st.id,
        status="stale" if stale else "ok",
        source=src,
        office=row.office,
        update_time=_utc(row.update_time),
        fetched_at=fetched,
        today_high_f=t.temperature_f if t else None,
        today_note=note,
        tonight_low_f=n.temperature_f if n else None,
        today=_period_out(t),
        tonight=_period_out(n),
        hourly=[
            s.HourSlotOut(
                start=h.start,
                temperature_f=h.temperature_f,
                pop_percent=h.pop_percent,
                short=h.short,
            )
            for h in hourly_strip(_periods(row.hourly), now)
        ],
        weather_gov_url=url,
    )
