"""GRIB model ingest: GFS, IFS, AIFS at the registry stations (CONTEXT §4.4).

Per poll and model: find the newest cycle whose step-0 index exists; download only the
fields we plot (byte ranges) for every step not fetched yet; extract all active stations in
one pass per message; store values step by step so a partial run is visible and grows as steps
arrive. Steps run to +54 h. Space: nearest land grid point (lsm >= 0.5) from the run's own
land-sea mask; height from the run's orography. Time: native steps only.
"""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.model_catalog import BY_ID
from edgefront_core.model_store import (
    NativeValue,
    StationResult,
    add_values,
    apply_retention,
    get_run,
    set_station_row,
    upsert_run,
)
from edgefront_core.models import ModelRun, Station
from edgefront_core.source_health import record_failure, record_success
from edgefront_core.timeutil import as_utc, utcnow
from edgefront_worker.grib.fields import (
    Field,
    GribError,
    StationPoint,
    decode,
    height_m,
    nearest_land_point,
)
from edgefront_worker.grib.sources import (
    GFS_AWS,
    GFS_NOMADS,
    Fetcher,
    MessageRef,
    ecmwf_url,
    gfs_patterns,
    gfs_url,
    parse_ecmwf_index,
    parse_wgrib_idx,
)
from edgefront_worker.memory import rss_mb

log = logging.getLogger("edgefront.models.grib")
MAX_LEAD_H = 54


@dataclass(frozen=True)
class GribModel:
    id: str
    steps: tuple[int, ...]
    opendata_name: str | None = None  # ECMWF open-data model name


GRIB_MODELS = {
    "gfs": GribModel("gfs", tuple(range(0, MAX_LEAD_H + 1))),
    "ifs": GribModel("ifs", tuple(range(0, MAX_LEAD_H + 1, 3)), "ifs"),
    "aifs": GribModel("aifs", tuple(range(0, MAX_LEAD_H + 1, 6)), "aifs-single"),
}
UNITS = {"K": "K", "%": "pct", "(0 - 1)": "fraction", "m s**-1": "m/s"}
VARIABLE_OF = {"temp": "temp", "dewpt": "dewpt", "rh": "rh", "cloud": "cloud"}


@dataclass
class GribRunSummary:
    model: str
    cycle: datetime | None = None
    status: str = "no_cycle"  # no_cycle | up_to_date | partial | complete
    steps_new: list[int] = field(default_factory=list)
    steps_total: int = 0
    stations: int = 0
    values: int = 0
    bytes: int = 0
    requests: int = 0
    seconds: float = 0.0
    rss_mb_after: float | None = None
    peak_rss_mb: float | None = None
    sources: dict[str, int] = field(default_factory=dict)


@dataclass
class _Station:
    id: str
    lat: float
    lon: float
    point: StationPoint | None = None


def candidate_cycles(now: datetime) -> list[datetime]:
    six = now.replace(hour=now.hour - now.hour % 6, minute=0, second=0, microsecond=0)
    return [six - timedelta(hours=6 * k) for k in range(5)]


def _notes(run: ModelRun | None) -> tuple[set[int], dict[str, tuple[int, int]]]:
    """(steps fetched, station grid indices) kept in model_runs.notes for partial runs."""
    if run is None or not run.notes:
        return set(), {}
    try:
        data = json.loads(run.notes)
        steps = {int(x) for x in data.get("steps", [])}
        points = {k: (int(v[0]), int(v[1])) for k, v in data.get("points", {}).items()}
    except (ValueError, TypeError, AttributeError, IndexError):
        return set(), {}
    return steps, points


class GribModelIngest:
    def __init__(
        self,
        client: httpx.Client,
        *,
        sleep: Callable[[float], None] = time.sleep,
        models: dict[str, GribModel] | None = None,
    ) -> None:
        self.fetch = Fetcher(client, sleep=sleep)
        self.models = models or GRIB_MODELS

    # -- locating messages

    def locate(
        self, model: GribModel, cycle: datetime, step: int
    ) -> tuple[dict[str, MessageRef], str] | None:
        """Message refs for one step, or None when the step is not published yet."""
        if model.opendata_name is None:
            for name, base in (("aws", GFS_AWS), ("nomads", GFS_NOMADS)):
                url = gfs_url(base, cycle, step)
                idx = self.fetch.text(url + ".idx")
                if idx is not None:
                    return parse_wgrib_idx(idx, url, gfs_patterns(step)), name
            return None
        url = ecmwf_url(model.opendata_name, cycle, step)
        idx = self.fetch.text(url.removesuffix(".grib2") + ".index")
        if idx is None:
            return None
        return parse_ecmwf_index(idx, url, with_static=step == 0), "ecmwf"

    # -- run

    def run(
        self, factory: sessionmaker[Session], model_id: str, now: datetime | None = None
    ) -> GribRunSummary:
        info = BY_ID[model_id]
        now = now or utcnow()
        t0 = time.monotonic()
        summary = GribRunSummary(model_id)
        self.fetch.bytes = self.fetch.requests = 0
        try:
            self._run(factory, self.models[model_id], now, summary)
        except Exception as exc:
            with session_scope(factory) as s:
                record_failure(s, info.source_key, utcnow(), f"{type(exc).__name__}: {exc}")
            log.exception("grib ingest failed", extra={"source": info.source_key})
            raise
        finally:
            summary.bytes, summary.requests = self.fetch.bytes, self.fetch.requests
            summary.seconds = round(time.monotonic() - t0, 1)
            summary.rss_mb_after, summary.peak_rss_mb = rss_mb()
        with session_scope(factory) as s:
            run = get_run(s, model_id, summary.cycle) if summary.cycle else None
            record_success(
                s,
                info.source_key,
                utcnow(),
                last_item_time=run.cycle_time if run else None,
                notes=f"{summary.status}; {summary.steps_total} steps",
            )
        log.info(
            "grib ingest",
            extra={
                "source": info.source_key,
                "cycle": summary.cycle.isoformat() if summary.cycle else None,
                "status": summary.status,
                "steps_new": summary.steps_new,
                "steps_total": summary.steps_total,
                "stations": summary.stations,
                "values": summary.values,
                "mb": round(summary.bytes / 1e6, 1),
                "requests": summary.requests,
                "seconds": summary.seconds,
                "rss_mb": summary.rss_mb_after,
                "peak_rss_mb": summary.peak_rss_mb,
                "sources": summary.sources,
            },
        )
        return summary

    def _run(
        self,
        factory: sessionmaker[Session],
        model: GribModel,
        now: datetime,
        summary: GribRunSummary,
    ) -> None:
        with session_scope(factory) as s:
            stations = [
                _Station(sid, lat, lon)
                for sid, lat, lon in s.execute(
                    select(Station.id, Station.lat, Station.lon).where(Station.active.is_(True))
                )
                if lat is not None and lon is not None
            ]
            runs = {
                as_utc(r.cycle_time): r
                for r in s.execute(select(ModelRun).where(ModelRun.model == model.id)).scalars()
            }
        summary.stations = len(stations)
        for cycle in candidate_cycles(now):
            run = runs.get(cycle)
            if run is not None and run.status == "complete":
                summary.cycle, summary.status = cycle, "up_to_date"
                summary.steps_total = run.steps_fetched
                return
            if run is None:
                first = self.locate(model, cycle, 0)
                if first is None:
                    continue  # not published yet: try the previous cycle
            summary.cycle = cycle
            self._ingest(factory, model, cycle, stations, run, now, summary)
            return

    def _ingest(
        self,
        factory: sessionmaker[Session],
        model: GribModel,
        cycle: datetime,
        stations: list[_Station],
        run: ModelRun | None,
        now: datetime,
        summary: GribRunSummary,
    ) -> None:
        done, known_points = _notes(run)
        label = BY_ID[model.id].label
        for st in stations:
            if st.id in known_points:
                j, i = known_points[st.id]
                st.point = StationPoint(j, i, 0.0, 0.0, 0.0, 1.0, True)  # only j/i are used
        for step in model.steps:
            if step in done:
                continue
            located = self.locate(model, cycle, step)
            if located is None:
                break  # steps are published in order: stop at the first missing one
            refs, source = located
            summary.sources[source] = summary.sources.get(source, 0) + 1
            valid = cycle + timedelta(hours=step)
            with session_scope(factory) as s:
                first_url = next(iter(refs.values())).url if refs else None
                r = upsert_run(s, model.id, cycle, now=now, source_url=first_url)
                r.steps_expected = len(model.steps)
                if step == 0 or any(st.point is None for st in stations):
                    static = refs if step == 0 else (self.locate(model, cycle, 0) or ({}, ""))[0]
                    self._place_stations(s, r, static, stations, label)
                native = self._step_values(refs, cycle, step, valid, stations)
                for st in stations:
                    if st.point is not None:
                        summary.values += add_values(s, r, st.id, native.get(st.id, []))
                done.add(step)
                points = {st.id: [st.point.j, st.point.i] for st in stations if st.point}
                r.notes = json.dumps({"steps": sorted(done), "points": points})
                r.steps_fetched = len(done)
                r.fetched_at = utcnow()
                r.status = "complete" if len(done) == len(model.steps) else "partial"
                summary.steps_new.append(step)
                summary.steps_total = len(done)
                summary.status = r.status
                apply_retention(s, model.id)
        if not summary.steps_new:
            summary.status = "partial" if done else "no_cycle"
            summary.steps_total = len(done)

    def _place_stations(
        self,
        s: Session,
        run: ModelRun,
        refs: dict[str, MessageRef],
        stations: list[_Station],
        label: str,
    ) -> None:
        if "lsm" not in refs or "orog" not in refs:
            raise GribError("step 0 has no land-sea mask / orography")
        lsm = decode(self.fetch.message(refs["lsm"]))
        orog = decode(self.fetch.message(refs["orog"]))
        for st in stations:
            p = nearest_land_point(lsm, st.lat, st.lon)
            st.point = p
            set_station_row(
                s,
                run,
                StationResult(
                    st.id,
                    "ok",
                    None if p.is_land else f"no {label} land grid point within 4 cells",
                    point_name=None,
                    grid_lat=round(p.lat, 4),
                    grid_lon=round(p.lon, 4),
                    grid_distance_km=round(p.distance_km, 2),
                    height_m=height_m(orog, p),
                    land_fraction=round(p.land_fraction, 3),
                ),
            )
        del lsm, orog

    def _step_values(
        self,
        refs: dict[str, MessageRef],
        cycle: datetime,
        step: int,
        valid: datetime,
        stations: list[_Station],
    ) -> dict[str, list[NativeValue]]:
        out: dict[str, list[NativeValue]] = {st.id: [] for st in stations}
        wind: dict[str, Field] = {}
        for key in ("temp", "dewpt", "rh", "cloud", "u10", "v10"):
            ref = refs.get(key)
            if ref is None:
                continue  # product has no such field at this step: never derived
            f = decode(self.fetch.message(ref))
            self._check(f, cycle, step)
            if key in ("u10", "v10"):
                wind[key] = f
                continue
            unit = UNITS.get(f.units)
            if unit is None:
                raise GribError(f"{f.short_name}: unexpected units {f.units!r}")
            for st in stations:
                if st.point is not None:
                    out[st.id].append(
                        NativeValue(valid, VARIABLE_OF[key], f.at(st.point.j, st.point.i), unit)
                    )
            del f
        if "u10" in wind and "v10" in wind:
            for st in stations:
                if st.point is None:
                    continue
                u = wind["u10"].at(st.point.j, st.point.i)
                v = wind["v10"].at(st.point.j, st.point.i)
                if u is not None and v is not None:
                    out[st.id].append(NativeValue(valid, "wind", math.hypot(u, v), "m/s"))
        return out

    @staticmethod
    def _check(f: Field, cycle: datetime, step: int) -> None:
        if (f.data_date, f.data_time) != (int(cycle.strftime("%Y%m%d")), cycle.hour * 100):
            raise GribError(
                f"{f.short_name}: message is for {f.data_date} {f.data_time}, not {cycle}"
            )
        if f.step.split("-")[-1] != str(step):
            raise GribError(f"{f.short_name}: message step {f.step}, wanted {step}")
