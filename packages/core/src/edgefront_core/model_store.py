"""Write model runs, per-station results and values; apply retention (CONTEXT §4.4, §7, §9).

Shared by the text-bulletin ingest and the GRIB ingest. Values arrive in the product's native
unit and are stored canonical (degC, kt, pct, category) with the native value/unit kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from edgefront_core.model_catalog import RETAIN_RUNS
from edgefront_core.models import ModelRun, ModelRunStation, ModelValue
from edgefront_core.units import rh_percent

KT_PER_MPH = 1 / 1.150779448
KT_PER_MS = 1.943844492


def to_canonical(native_value: float | None, native_unit: str) -> tuple[float | None, str]:
    """(value, unit) in EdgeFront's stored units. Raises on a unit we never decided on."""
    if native_unit == "category":
        return None, "category"
    if native_value is None:
        return None, _CANON[native_unit]
    v = float(native_value)
    match native_unit:
        case "degF":
            return (v - 32.0) * 5.0 / 9.0, "degC"
        case "degC":
            return v, "degC"
        case "K":
            return v - 273.15, "degC"
        case "kt":
            return v, "kt"
        case "mph":
            return v * KT_PER_MPH, "kt"
        case "m/s":
            return v * KT_PER_MS, "kt"
        case "pct":
            return v, "pct"
        case "fraction":
            return v * 100.0, "pct"
    raise ValueError(f"unknown native unit {native_unit!r}")


_CANON = {
    "degF": "degC", "degC": "degC", "K": "degC", "kt": "kt", "mph": "kt", "m/s": "kt",
    "pct": "pct", "fraction": "pct",
}  # fmt: skip


@dataclass(frozen=True)
class NativeValue:
    valid_time: datetime
    variable: str
    value: float | None
    native_unit: str
    category: str | None = None


@dataclass
class StationResult:
    station_id: str
    status: str  # ok | not_available | failed
    reason: str | None = None
    values: list[NativeValue] = field(default_factory=list)
    point_name: str | None = None
    grid_lat: float | None = None
    grid_lon: float | None = None
    grid_distance_km: float | None = None
    height_m: float | None = None
    land_fraction: float | None = None


def build_values(native: list[NativeValue]) -> list[ModelValue]:
    """Canonical ModelValue rows (no run/station ids yet) + computed RH where the product has
    temp and dewpt at a time but no RH of its own."""
    rows: list[ModelValue] = []
    by_time: dict[datetime, dict[str, float]] = {}
    has_rh: set[datetime] = set()
    seen: set[tuple[datetime, str]] = set()
    for nv in native:
        key = (nv.valid_time, nv.variable)
        if key in seen:
            continue  # first value for a (time, variable) wins; products never repeat one
        seen.add(key)
        value, unit = to_canonical(nv.value, nv.native_unit)
        rows.append(
            ModelValue(
                valid_time=nv.valid_time,
                variable=nv.variable,
                value=value,
                unit=unit,
                native_value=nv.value,
                native_unit=nv.native_unit,
                category=nv.category,
                is_computed=False,
            )
        )
        if nv.variable == "rh":
            has_rh.add(nv.valid_time)
        if nv.variable in ("temp", "dewpt") and value is not None:
            by_time.setdefault(nv.valid_time, {})[nv.variable] = value
    for t, tv in sorted(by_time.items()):
        if t in has_rh or "temp" not in tv or "dewpt" not in tv:
            continue
        rows.append(
            ModelValue(
                valid_time=t,
                variable="rh",
                value=rh_percent(tv["temp"], tv["dewpt"]),
                unit="pct",
                native_value=None,
                native_unit=None,
                category=None,
                is_computed=True,
            )
        )
    return rows


def get_run(s: Session, model: str, cycle_time: datetime, issuer: str = "") -> ModelRun | None:
    return s.execute(
        select(ModelRun).where(
            ModelRun.model == model,
            ModelRun.cycle_time == cycle_time,
            ModelRun.issuer == issuer,
        )
    ).scalar_one_or_none()


def upsert_run(
    s: Session,
    model: str,
    cycle_time: datetime,
    *,
    now: datetime,
    issuer: str = "",
    source_url: str | None = None,
    available_at: datetime | None = None,
) -> ModelRun:
    run = get_run(s, model, cycle_time, issuer)
    if run is None:
        run = ModelRun(
            model=model,
            cycle_time=cycle_time,
            issuer=issuer,
            available_at=available_at or now,
            status="partial",
            steps_fetched=0,
        )
        s.add(run)
    if source_url is not None:
        run.source_url = source_url
    run.updated_at = now
    s.flush()
    return run


def store_station(s: Session, run: ModelRun, result: StationResult) -> int:
    """Replace this run's rows for one station. Returns the number of values written."""
    s.execute(
        delete(ModelValue).where(
            ModelValue.run_id == run.id, ModelValue.station_id == result.station_id
        )
    )
    s.execute(
        delete(ModelRunStation).where(
            ModelRunStation.run_id == run.id, ModelRunStation.station_id == result.station_id
        )
    )
    s.add(
        ModelRunStation(
            run_id=run.id,
            station_id=result.station_id,
            status=result.status,
            reason=result.reason,
            point_name=result.point_name,
            grid_lat=result.grid_lat,
            grid_lon=result.grid_lon,
            grid_distance_km=result.grid_distance_km,
            height_m=result.height_m,
            land_fraction=result.land_fraction,
        )
    )
    rows = build_values(result.values) if result.status == "ok" else []
    for r in rows:
        r.run_id = run.id
        r.station_id = result.station_id
    s.add_all(rows)
    s.flush()
    return len(rows)


def apply_retention(s: Session, model: str, keep: int = RETAIN_RUNS) -> int:
    """Keep the newest `keep` runs per (model, issuer). Explicit child deletes (SQLite has no
    enforced cascade). Returns the number of runs deleted."""
    runs = s.execute(
        select(ModelRun.id, ModelRun.issuer)
        .where(ModelRun.model == model)
        .order_by(ModelRun.issuer, ModelRun.cycle_time.desc())
    ).all()
    count: dict[str, int] = {}
    doomed: list[int] = []
    for run_id, issuer in runs:
        count[issuer] = count.get(issuer, 0) + 1
        if count[issuer] > keep:
            doomed.append(run_id)
    if doomed:
        s.execute(delete(ModelValue).where(ModelValue.run_id.in_(doomed)))
        s.execute(delete(ModelRunStation).where(ModelRunStation.run_id.in_(doomed)))
        s.execute(delete(ModelRun).where(ModelRun.id.in_(doomed)))
    return len(doomed)
