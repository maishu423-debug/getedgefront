"""Ingest of the station text guidance: NBM (NBH + NBS), GFS-MOS (MAV), LAMP (LAV) from NOMADS
and the PFM from api.weather.gov (CONTEXT §4.4; formats in docs/formats/model_text.md, pfm.md).

Called by the worker only. Per poll and model: find the newest cycle that exists upstream; if
we don't have it complete, download it, decode the blocks of every active station in one pass
and store them. A station missing from a bulletin is stored as `not_available`; a block that
fails to decode is `failed` with the reason (never guessed). Latest 4 runs kept.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.http import get_with_retry
from edgefront_core.model_catalog import BY_ID
from edgefront_core.model_store import (
    NativeValue,
    StationResult,
    apply_retention,
    get_run,
    store_station,
    upsert_run,
)
from edgefront_core.models import ModelRun, Station
from edgefront_core.nws_products import NwsProductLister
from edgefront_core.parsers.model_text import StationGuidance, decode_bulletin
from edgefront_core.parsers.pfm import PfmDecodeError, decode_point, find_block
from edgefront_core.parsers.stations import km_between
from edgefront_core.source_health import record_failure, record_success
from edgefront_core.timeutil import as_utc, utcnow

log = logging.getLogger("edgefront.models.text")
NOMADS = "https://nomads.ncep.noaa.gov/pub/data/nccf/com"


def nomads_url(product: str, cycle: datetime) -> str:
    day, hh = cycle.strftime("%Y%m%d"), cycle.strftime("%H")
    match product:
        case "nbh":
            return f"{NOMADS}/blend/prod/blend.{day}/{hh}/text/blend_nbhtx.t{hh}z"
        case "nbs":
            return f"{NOMADS}/blend/prod/blend.{day}/{hh}/text/blend_nbstx.t{hh}z"
        case "mav":
            return f"{NOMADS}/gfs_mos/prod/gfs_mos.{day}/mdl_gfsmav.t{hh}z"
        case "lav":
            return f"{NOMADS}/lmp/prod/lmp.{day}/lmp.t{hh}{cycle:%M}z.lavtxt.ascii"
        case "lavx":  # extended LAMP, hours 26-38 (owner Q27)
            return f"{NOMADS}/lmp/prod/lmp.{day}/lmp.t{hh}{cycle:%M}z.lavtxt_ext.ascii"
    raise ValueError(product)


# model id -> bulletins that make one run, in order
FILES: dict[str, tuple[str, ...]] = {
    "nbm": ("nbh", "nbs"),
    "gfs_mos": ("mav",),
    "lamp": ("lav", "lavx"),
}


def candidate_cycles(model: str, now: datetime) -> list[datetime]:
    """Cycles that could be the newest one upstream, newest first."""
    hour = now.replace(minute=0, second=0, microsecond=0)
    if model == "nbm":
        return [hour - timedelta(hours=h) for h in range(6)]
    if model == "lamp":
        start = hour.replace(minute=30) if now.minute >= 30 else hour - timedelta(minutes=30)
        return [start - timedelta(hours=h) for h in range(6)]
    if model == "gfs_mos":
        six = hour.replace(hour=hour.hour - hour.hour % 6)
        return [six - timedelta(hours=6 * k) for k in range(4)]
    raise ValueError(model)


def exists(client: httpx.Client, url: str, sleep: Callable[[float], None]) -> bool:
    """HEAD the file. 200 → True, 404 → False; other answers are retried, then raise."""
    last = ""
    for attempt in range(3):
        try:
            r = client.head(url)
        except httpx.TransportError as e:
            last = f"{type(e).__name__}: {e}"
        else:
            if r.status_code == 200:
                return True
            if r.status_code in (403, 404):
                return False
            last = f"HTTP {r.status_code}"
        sleep(2.0 * (attempt + 1))
    raise httpx.HTTPError(f"HEAD {url}: {last}")


def _native(g: StationGuidance) -> list[NativeValue]:
    return [
        NativeValue(v.valid_time, v.variable, v.value, v.native_unit, v.category) for v in g.values
    ]


def merge_tail(head: StationGuidance | None, tail: StationGuidance | None) -> list[NativeValue]:
    """`head` first; `tail` only beyond head's last valid time for each variable.

    NBM: NBH hourly, then NBS 3-hourly. LAMP: the 25 h bulletin, then the extended one."""
    out = _native(head) if head else []
    if tail:
        last: dict[str, datetime] = {}
        for v in out:
            last[v.variable] = max(last.get(v.variable, v.valid_time), v.valid_time)
        out += [
            v for v in _native(tail) if v.variable not in last or v.valid_time > last[v.variable]
        ]
    return out


@dataclass
class TextRunSummary:
    model: str
    cycle: datetime | None = None
    status: str = "up_to_date"  # up_to_date | no_cycle | partial | complete
    files: list[str] = field(default_factory=list)
    stations_ok: int = 0
    stations_missing: list[str] = field(default_factory=list)
    stations_failed: dict[str, str] = field(default_factory=dict)
    values: int = 0
    bytes: int = 0
    deleted_runs: int = 0


def _station_ids(s: Session) -> list[str]:
    return list(s.execute(select(Station.id).where(Station.active.is_(True))).scalars())


class TextModelIngest:
    def __init__(
        self, client: httpx.Client, *, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self.client = client
        self.sleep = sleep

    def run(
        self, factory: sessionmaker[Session], model: str, now: datetime | None = None
    ) -> TextRunSummary:
        info = BY_ID[model]
        now = now or utcnow()
        summary = TextRunSummary(model)
        try:
            self._run(factory, model, now, summary)
        except Exception as exc:
            with session_scope(factory) as s:
                record_failure(s, info.source_key, utcnow(), f"{type(exc).__name__}: {exc}")
            log.exception("model text ingest failed", extra={"source": info.source_key})
            raise
        with session_scope(factory) as s:
            run = get_run(s, model, summary.cycle) if summary.cycle is not None else None
            record_success(
                s,
                info.source_key,
                utcnow(),
                last_item_time=run.cycle_time if run else None,
                notes=f"{summary.status}; {summary.stations_ok} stations",
            )
        log.info(
            "model text ingest",
            extra={
                "source": info.source_key,
                "cycle": summary.cycle.isoformat() if summary.cycle else None,
                "status": summary.status,
                "files": summary.files,
                "stations_ok": summary.stations_ok,
                "missing": summary.stations_missing,
                "failed": summary.stations_failed,
                "values": summary.values,
                "bytes": summary.bytes,
                "deleted_runs": summary.deleted_runs,
            },
        )
        return summary

    def _run(
        self, factory: sessionmaker[Session], model: str, now: datetime, summary: TextRunSummary
    ) -> None:
        files = FILES[model]
        with session_scope(factory) as s:
            ids = _station_ids(s)
            known = {
                as_utc(r.cycle_time): (r.status, (r.notes or "").split(","))
                for r in s.execute(select(ModelRun).where(ModelRun.model == model)).scalars()
            }
        for cycle in candidate_cycles(model, now):
            st = known.get(cycle)
            if st and st[0] == "complete":
                summary.cycle = cycle
                return  # newest cycle already complete
            if not exists(self.client, nomads_url(files[0], cycle), self.sleep):
                continue
            summary.cycle = cycle
            have = [f for f in (st[1] if st else []) if f]
            missing = [f for f in files if f not in have]
            if have and not any(
                exists(self.client, nomads_url(f, cycle), self.sleep) for f in missing
            ):
                summary.status = "partial"  # still waiting for e.g. the NBS; don't re-download
                return
            self._ingest(factory, model, cycle, ids, have, now, summary)
            return
        summary.status = "no_cycle"

    def _ingest(
        self,
        factory: sessionmaker[Session],
        model: str,
        cycle: datetime,
        ids: list[str],
        have: list[str],
        now: datetime,
        summary: TextRunSummary,
    ) -> None:
        files = FILES[model]
        decoded: dict[str, dict[str, StationGuidance]] = {}
        errors: dict[str, dict[str, str]] = {}
        got: list[str] = []
        for f in files:
            url = nomads_url(f, cycle)
            r = get_with_retry(self.client, url, sleep=self.sleep)
            if r.status_code == 404:
                continue  # e.g. NBS not out yet: run stays partial
            r.raise_for_status()
            summary.bytes += len(r.content)
            d, e = decode_bulletin(r.content.decode("ascii", errors="replace"), ids)
            decoded[f], errors[f] = d, e
            got.append(f)
        summary.files = got
        if not got:
            summary.status = "no_cycle"
            return
        label = BY_ID[model].label
        with session_scope(factory) as s:
            run = upsert_run(s, model, cycle, now=now, source_url=nomads_url(files[0], cycle))
            run.fetched_at = utcnow()
            run.steps_expected = len(files)
            run.steps_fetched = len(got)
            run.notes = ",".join(got)
            run.status = "complete" if len(got) == len(files) else "partial"
            summary.status = run.status
            for sid in ids:
                err = next((errors[f][sid] for f in got if sid in errors[f]), None)
                blocks = {f: decoded[f].get(sid) for f in got}
                if err:
                    res = StationResult(sid, "failed", f"decode error: {err}")
                    summary.stations_failed[sid] = err
                elif not any(blocks.values()):
                    res = StationResult(
                        sid, "not_available", f"Not in the {label} station bulletin"
                    )
                    summary.stations_missing.append(sid)
                else:
                    if len(files) == 2:
                        native = merge_tail(blocks.get(files[0]), blocks.get(files[1]))
                    else:
                        native = _native(next(b for b in blocks.values() if b))
                    cell_errors = [x for b in blocks.values() if b for x in b.decode_errors]
                    res = StationResult(
                        sid,
                        "ok",
                        f"{len(cell_errors)} cells not decoded" if cell_errors else None,
                        native,
                        point_name=sid,
                    )
                    summary.stations_ok += 1
                summary.values += store_station(s, run, res)
            summary.deleted_runs = apply_retention(s, model)


# ---------------------------------------------------------------- PFM


@dataclass
class PfmRunSummary:
    offices: int = 0
    new_products: int = 0
    stations_ok: int = 0
    stations_failed: dict[str, str] = field(default_factory=dict)
    values: int = 0
    deleted_runs: int = 0


class PfmIngest:
    MODEL = "pfm"

    def __init__(self, lister: NwsProductLister) -> None:
        self.lister = lister

    def run(self, factory: sessionmaker[Session], now: datetime | None = None) -> PfmRunSummary:
        info = BY_ID[self.MODEL]
        now = now or utcnow()
        summary = PfmRunSummary()
        try:
            self._run(factory, now, summary)
        except Exception as exc:
            with session_scope(factory) as s:
                record_failure(s, info.source_key, utcnow(), f"{type(exc).__name__}: {exc}")
            log.exception("pfm ingest failed", extra={"source": info.source_key})
            raise
        with session_scope(factory) as s:
            newest = s.execute(
                select(ModelRun.cycle_time)
                .where(ModelRun.model == self.MODEL)
                .order_by(ModelRun.cycle_time.desc())
                .limit(1)
            ).scalar_one_or_none()
            record_success(
                s,
                info.source_key,
                utcnow(),
                last_item_time=newest,
                notes=f"{summary.new_products} new products, {summary.offices} offices",
            )
        log.info(
            "pfm ingest",
            extra={
                "source": info.source_key,
                "offices": summary.offices,
                "new_products": summary.new_products,
                "stations_ok": summary.stations_ok,
                "failed": summary.stations_failed,
                "values": summary.values,
                "deleted_runs": summary.deleted_runs,
            },
        )
        return summary

    def _run(self, factory: sessionmaker[Session], now: datetime, summary: PfmRunSummary) -> None:
        with session_scope(factory) as s:
            stations = s.execute(
                select(
                    Station.id, Station.nws_office, Station.pfm_point, Station.lat, Station.lon
                ).where(
                    Station.active.is_(True),
                    Station.pfm_point.is_not(None),
                    Station.nws_office.is_not(None),
                )
            ).all()
            known: dict[str, tuple[set[str], datetime | None]] = {}
            for r in s.execute(select(ModelRun).where(ModelRun.model == self.MODEL)).scalars():
                ids, newest = known.get(r.issuer, (set(), None))
                ids.add((r.source_url or "").rsplit("/", 1)[-1])
                ct = as_utc(r.cycle_time)
                known[r.issuer] = (ids, max(newest, ct) if newest else ct)
        by_office: dict[str, list[tuple[str, str, float | None, float | None]]] = {}
        for sid, office, point, lat, lon in stations:
            if office and point:  # both filtered non-null in the query
                by_office.setdefault(office, []).append((sid, point, lat, lon))
        summary.offices = len(by_office)
        for office, points in sorted(by_office.items()):
            ids, newest = known.get(office, (set(), None))
            since = newest + timedelta(seconds=1) if newest else now - timedelta(hours=12)
            products = self.lister.new_products("PFM", office, ids, since=since)
            for p in sorted(products, key=lambda x: x.issued_at):
                summary.new_products += 1
                with session_scope(factory) as s:
                    run = upsert_run(
                        s, self.MODEL, p.issued_at, now=now, issuer=office, source_url=p.url
                    )
                    run.fetched_at = utcnow()
                    run.steps_expected = run.steps_fetched = 1
                    run.status = "complete"
                    for sid, point, lat, lon in points:
                        res = self._station(sid, point, office, p.text, lat, lon)
                        if res.status == "ok":
                            summary.stations_ok += 1
                        else:
                            summary.stations_failed[sid] = res.reason or ""
                        summary.values += store_station(s, run, res)
                    summary.deleted_runs += apply_retention(s, self.MODEL)

    @staticmethod
    def _station(
        sid: str, point: str, office: str, text: str, lat: float | None, lon: float | None
    ) -> StationResult:
        block = find_block(text, point)
        if block is None:
            return StationResult(sid, "not_available", f"Point '{point}' not in this PFM{office}")
        try:
            fc = decode_point(block)
        except PfmDecodeError as e:
            return StationResult(sid, "failed", f"decode error: {e}", point_name=point)
        return StationResult(
            sid,
            "ok",
            f"{len(fc.decode_errors)} cells not decoded" if fc.decode_errors else None,
            [
                NativeValue(v.valid_time, v.variable, v.value, v.native_unit, v.category)
                for v in fc.values
            ],
            point_name=point,
            grid_lat=fc.lat,
            grid_lon=fc.lon,
            grid_distance_km=(
                round(km_between(lat, lon, fc.lat, fc.lon), 2)
                if lat is not None and lon is not None
                else None
            ),
            height_m=round(fc.elev_ft * 0.3048, 1) if fc.elev_ft is not None else None,
        )
