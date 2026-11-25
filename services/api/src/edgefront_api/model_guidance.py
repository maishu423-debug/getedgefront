"""GET /stations/{id}/models — model guidance for one station and variable (CONTEXT §8, §10.3.7).

Reads Postgres only. Per model: the newest run that has this station; its values at native valid
times inside the window (no interpolation); the observed METAR line for the same variable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from edgefront_api import schemas as s
from edgefront_api.services import (
    _metar_source,
    _reports,
    _sky,
    _sky_cover,
    climate_day_out,
    std_offset_minutes,
    utc,
)
from edgefront_core.climate import effective_reports
from edgefront_core.model_catalog import MODELS, ModelInfo
from edgefront_core.models import ModelRun, ModelRunStation, ModelValue, Station
from edgefront_core.units import CLOUD_MIDPOINT, c_to_f_display, rh_percent

DISPLAY_UNIT: dict[str, Literal["degF", "kt", "pct"]] = {
    "temp": "degF", "dewpt": "degF", "wind": "kt", "cloud": "pct", "rh": "pct",
}  # fmt: skip
VARIABLE_LABEL = {
    "temp": "temperature", "dewpt": "dew point", "wind": "wind", "cloud": "cloud", "rh": "RH",
}  # fmt: skip
# MOS / LAMP cloud codes → §6.5 plotting midpoints (METAR octa classes).
CATEGORY_MIDPOINT = {
    "CL": CLOUD_MIDPOINT["CLR"], "FW": CLOUD_MIDPOINT["FEW"], "SC": CLOUD_MIDPOINT["SCT"],
    "BK": CLOUD_MIDPOINT["BKN"], "OV": CLOUD_MIDPOINT["OVC"],
}  # fmt: skip
# PFM codes have their own sky-cover ranges (NWS "Point Forecast Matrices Product Specifications",
# Table 2 "PFM Sky Cover Codes"): plotted at the midpoint of each range (owner Q25).
PFM_CATEGORY: dict[str, tuple[float, str]] = {
    "CL": (2.5, "0% to ≤ 5%"),
    "FW": (15.0, "> 5% and ≤ 25%"),
    "SC": (37.5, "> 25% and ≤ 50%"),
    "B1": (59.5, "> 50% and ≤ 69%"),
    "B2": (78.0, "> 69% and ≤ 87%"),
    "OV": (93.5, "> 87% and ≤ 100%"),
}


def _whole(x: float) -> float:
    d = Decimal(str(x))
    r = abs(d).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return float(r if d >= 0 else -r)


def display_value(
    variable: str, value: float | None, category: str | None, model: str = ""
) -> float | None:
    """Canonical stored value → display unit (whole °F / kt / %); categories → midpoint."""
    if category is not None:
        if model == "pfm":
            return PFM_CATEGORY[category][0] if category in PFM_CATEGORY else None
        return float(CATEGORY_MIDPOINT[category]) if category in CATEGORY_MIDPOINT else None
    if value is None:
        return None
    if variable in ("temp", "dewpt"):
        return float(c_to_f_display(value))
    return _whole(value)


def window(st: Station, now: datetime, span: str) -> s.ModelWindow:
    day = climate_day_out(st, now)
    end = day.end if span == "today" else day.start + timedelta(hours=48)
    tz = timezone(timedelta(minutes=std_offset_minutes(st, now)))
    return s.ModelWindow(
        span=cast(Literal["today", "48h"], span),
        start=day.start,
        end=end,
        start_local=day.start.astimezone(tz),
        end_local=end.astimezone(tz),
        climate_date=day.date,
        basis=day.basis,
    )


def _observed(
    session: Session, st: Station, variable: str, w: s.ModelWindow, now: datetime
) -> s.ObservedOverlay:
    reps = effective_reports(_reports(session, [st.id], w.start))
    pts: list[s.ModelPoint] = []
    for r in reps:
        if r.observed_at > min(now, w.end):
            break
        m = r.row
        value: float | None
        cat: str | None = None
        comp = False
        match variable:
            case "temp":
                value = None if m.temp_c is None else float(c_to_f_display(m.temp_c))
            case "dewpt":
                value = None if m.dewpt_c is None else float(c_to_f_display(m.dewpt_c))
            case "wind":
                value = None if m.wind_kt is None else float(m.wind_kt)
            case "rh":
                rh = rh_percent(m.temp_c, m.dewpt_c)
                value, comp = (None if rh is None else _whole(rh)), True
            case _:  # cloud: greatest reported cover → midpoint
                cat = _sky_cover(_sky(m))
                value = None if cat is None else float(CLOUD_MIDPOINT.get(cat, 0))
        if value is not None:
            pts.append(
                s.ModelPoint(valid_time=r.observed_at, value=value, category=cat, is_computed=comp)
            )
    return s.ObservedOverlay(source=_metar_source(session), points=pts)


def _latest_rows(
    session: Session, st: Station, info: ModelInfo
) -> tuple[ModelRun, ModelRunStation] | tuple[ModelRun, None] | None:
    """Newest run with an `ok` row for this station; else the newest run (row may be missing)."""
    q = (
        select(ModelRun, ModelRunStation)
        .join(ModelRunStation, ModelRunStation.run_id == ModelRun.id)
        .where(ModelRun.model == info.id, ModelRunStation.station_id == st.id)
        .order_by(ModelRun.cycle_time.desc(), ModelRun.id.desc())
    )
    if info.id == "pfm":
        q = q.where(ModelRun.issuer == (st.nws_office or ""))
    rows = session.execute(q.limit(8)).all()
    for run, rs in rows:
        if rs.status == "ok":
            return run, rs
    if rows:
        return rows[0][0], rows[0][1]
    newest = session.execute(
        select(ModelRun)
        .where(ModelRun.model == info.id)
        .order_by(ModelRun.cycle_time.desc())
        .limit(1)
    ).scalar_one_or_none()
    return (newest, None) if newest else None


def _run_out(run: ModelRun, info: ModelInfo, now: datetime) -> s.ModelRunOut:
    avail = utc(run.available_at)
    return s.ModelRunOut(
        cycle_time=utc(run.cycle_time),
        issuer=run.issuer or None,
        available_at=avail,
        fetched_at=utc(run.fetched_at) if run.fetched_at else None,
        status=cast(Literal["partial", "complete", "failed"], run.status),
        steps_expected=run.steps_expected,
        steps_fetched=run.steps_fetched,
        source_url=run.source_url,
        stale=(now - avail) > 2 * info.cycle_interval,
    )


def _series(
    session: Session, st: Station, info: ModelInfo, variable: str, w: s.ModelWindow, now: datetime
) -> s.ModelSeries:
    base = {
        "id": info.id,
        "label": info.label,
        "group": info.group,
        "producer": info.producer,
        "colour_token": info.colour_token,
        "licence": info.licence,
        "native_step_hours": list(info.native_step_hours),
    }

    def unavailable(code: str, reason: str, run: s.ModelRunOut | None = None) -> s.ModelSeries:
        return s.ModelSeries(
            **base,
            available=False,
            reason=reason,
            reason_code=cast(
                Literal["no_run", "no_station", "no_variable", "station_failed"], code
            ),
            kind=None,
            native_unit=None,
            run=run,
            grid=None,
            points=[],
        )

    if info.id == "pfm" and not st.pfm_point:
        return unavailable("no_station", "Not available for this station (no PFM point)")
    if variable not in info.variables:
        return unavailable("no_variable", f"no {VARIABLE_LABEL[variable]}")
    found = _latest_rows(session, st, info)
    if found is None:
        return unavailable("no_run", f"No {info.label} run received yet")
    run, rs = found
    run_out = _run_out(run, info, now)
    if rs is None:
        return unavailable(
            "no_station", f"Not available for this station (not in the {info.label} run)", run_out
        )
    if rs.status == "not_available":
        return unavailable("no_station", rs.reason or "Not available for this station", run_out)
    if rs.status == "failed":
        return unavailable("station_failed", rs.reason or "Could not decode this run", run_out)

    rows = session.execute(
        select(ModelValue)
        .where(
            ModelValue.run_id == run.id,
            ModelValue.station_id == st.id,
            ModelValue.variable == variable,
            ModelValue.valid_time >= w.start,
            ModelValue.valid_time <= w.end,
        )
        .order_by(ModelValue.valid_time)
    ).scalars()
    points = [
        s.ModelPoint(
            valid_time=utc(v.valid_time),
            value=display_value(variable, v.value, v.category, info.id),
            category=v.category,
            category_range=(
                PFM_CATEGORY[v.category][1]
                if info.id == "pfm" and v.category in PFM_CATEGORY
                else None
            ),
            is_computed=v.is_computed,
        )
        for v in rows
    ]
    any_value = session.execute(
        select(ModelValue.native_unit, ModelValue.category)
        .where(
            ModelValue.run_id == run.id,
            ModelValue.station_id == st.id,
            ModelValue.variable == variable,
        )
        .limit(1)
    ).first()
    if any_value is None:
        return unavailable("no_variable", f"no {VARIABLE_LABEL[variable]}", run_out)
    native_unit, category = any_value
    return s.ModelSeries(
        **base,
        available=True,
        kind="categorical" if category is not None else "continuous",
        native_unit=native_unit or ("computed" if variable == "rh" else None),
        run=run_out,
        grid=s.ModelGrid(
            lat=rs.grid_lat,
            lon=rs.grid_lon,
            distance_km=rs.grid_distance_km,
            height_m=rs.height_m,
            point_name=rs.point_name,
        ),
        points=points,
    )


def models(
    session: Session, st: Station, now: datetime, variable: str, span: str
) -> s.ModelsResponse:
    w = window(st, now, span)
    return s.ModelsResponse(
        generated_at=now,
        station_id=st.id,
        station_name=st.name,
        variable=cast(s.ModelVariable, variable),
        unit=DISPLAY_UNIT[variable],
        now=now,
        window=w,
        observed=_observed(session, st, variable, w, now),
        models=[_series(session, st, m, variable, w, now) for m in MODELS],
    )
