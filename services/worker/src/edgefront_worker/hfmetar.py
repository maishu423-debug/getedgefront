"""`hfmetar` job (v2 Phase 9 B5): 5-minute MADIS "1-minute ASOS" files from the owner's LDM API.

Every ~60 s: GET /health, GET /api/v1/hfmetar/files, download only files whose (modified_at, size)
changed since we processed them (`hf_files`), gunzip + open the netCDF-3 file in memory, keep our
registry stations, upsert `hf_observations` (edgefront_core.hf_store). Format and grids:
docs/formats/hfmetar.md. Values are snapped to their verified grid; a value off its grid is
flagged in `qc.off_grid` (raw value kept there), never guessed. Missing stays null.

Alerts (structured log lines at ERROR, repeated hourly while active, "resolved" at WARNING):
- `ldm_health`: the LDM API's /health fails;
- `no_new_readings`: /health is ok but no new 5-minute reading has been stored for 15 minutes.
"""

from __future__ import annotations

import io
import logging
import math
import re
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
import numpy as np
from scipy.io import netcdf_file
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.hf_store import SOURCE, HfReading, last_ingested_at, upsert_readings
from edgefront_core.http import UpstreamError, get_with_retry
from edgefront_core.models import HfFile, HfObservation, Station
from edgefront_core.source_health import record_failure, record_success
from edgefront_core.timeutil import as_utc, utcnow
from edgefront_worker.memory import rss_mb

log = logging.getLogger("edgefront.worker.hfmetar")

NAME_RE = re.compile(r"^hfmetar\.(\d{8})_(\d{2})00\.gz$")
PROVIDERS = frozenset({"HF-METAR"})  # MADIS distribution category 3 (docs/sources.md#hfmetar)
MAX_GZ_BYTES = 20 * 1024 * 1024  # real files: ~1.3 MB
MAX_RAW_BYTES = 120 * 1024 * 1024  # real files: ~19 MB uncompressed
KT_PER_MS = Decimal(3600) / Decimal(1852)
PA_PER_INHG = Decimal("3386.389")
M_PER_MI = Decimal("1609.344")
MM_PER_IN = Decimal("25.4")
QC_VARS = (
    "temperature", "dewpoint", "windDir", "windSpeed", "windGust", "altimeter", "visibility",
    "precipAccum",
)  # fmt: skip
NEEDED = (
    "observationTime",
    "receivedTime",
    "rawMessage",
    "skyCvr",
    "skyCovLayerBase",
    "presWx",
    *(f"{q}{s}" for q in QC_VARS for s in ("", "DD", "QCA", "QCR")),
)
ALERT_REPEAT = timedelta(hours=1)


# ---------------------------------------------------------------- parsing


def _num(x: Any) -> float | None:
    v = float(x)
    if not math.isfinite(v) or abs(v) > 1e30 or v == -9999.0:
        return None  # _FillValue 3.4028235e+38 / missing_value -9999
    return v


def _snap(x: Decimal, step: Decimal, tol: Decimal) -> Decimal | None:
    """x on the grid of `step` (within `tol`) → the grid value; else None."""
    n = (x / step).to_integral_value(ROUND_HALF_EVEN)
    return n * step if abs(x - n * step) <= tol else None


@dataclass
class _Row:
    reading: HfReading
    off_grid: int


def _temp(
    raw_k: float | None, off: dict[str, float], var: str
) -> tuple[Decimal | None, str | None]:
    if raw_k is None:
        return None, None
    c = Decimal(repr(raw_k)) - Decimal("273.15")
    whole = _snap(c, Decimal(1), Decimal("0.01"))
    if whole is not None:
        return whole.quantize(Decimal(1)), "whole_c"
    tenths = _snap(c, Decimal("0.1"), Decimal("0.01"))
    if tenths is not None:
        return tenths.quantize(Decimal("0.1")), "tenths_c"
    off[var] = raw_k
    return c.quantize(Decimal("0.01")), "off_grid"


def _grid_int(raw: float | None, scale: Decimal, off: dict[str, float], var: str) -> int | None:
    if raw is None:
        return None
    v = _snap(Decimal(repr(raw)) * scale, Decimal(1), Decimal("0.01"))
    if v is None:
        off[var] = raw
        return None  # an integer column cannot hold the raw value: kept in qc.off_grid
    return int(v)


def _grid_dec(
    raw: float | None, divisor: Decimal, step: Decimal, off: dict[str, float], var: str,
    places: Decimal,
) -> Decimal | None:  # fmt: skip
    if raw is None:
        return None
    x = Decimal(repr(raw)) / divisor
    v = _snap(x, step, step / 10)
    if v is None:
        off[var] = raw
        return x.quantize(places)
    return v.quantize(places)


def _text(row: Any) -> str:
    return b"".join(row).decode("ascii", "replace").strip("\x00").strip()


def _char(v: Any) -> str | None:
    s = bytes(v).decode("ascii", "replace").strip("\x00").strip()
    return s or None


FT_PER_M = Decimal(1) / Decimal("0.3048")


def _sky(covers: Any, bases: Any) -> list[dict[str, Any]] | None:
    """Sky layers as reported ([{"cover": "BKN", "base_ft": 1500}]); bases in the file are metres
    of a value reported in hundreds of feet, so they snap back to whole hundreds (else whole feet).
    CLR has no base (the file carries the sensor's 12,500 ft limit there)."""
    out: list[dict[str, Any]] = []
    for c, b in zip(covers, bases, strict=False):
        cover = _text(c)
        if not cover:
            continue
        m = _num(b)
        base = None
        if m is not None and cover not in ("CLR", "SKC"):
            ft = Decimal(repr(m)) * FT_PER_M
            hundreds = (ft / 100).to_integral_value() * 100
            base = int(hundreds) if abs(ft - hundreds) <= 2 else int(ft.to_integral_value())
        out.append({"cover": cover, "base_ft": base})
    return out or None


@dataclass
class ParsedFile:
    records: int = 0  # every record in the file (all stations)
    readings: list[HfReading] = field(default_factory=list)  # ours, one per (station, time)
    duplicates: int = 0  # same station + time twice in one file (later receivedTime kept)
    skipped_provider: int = 0  # dataProvider other than HF-METAR (would be restricted data)
    bad_time: int = 0
    off_grid: int = 0  # values flagged off their grid
    raw_bytes: int = 0


def gunzip_capped(data: bytes, limit: int = MAX_RAW_BYTES) -> bytes:
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = d.decompress(data, limit)
    if d.unconsumed_tail:
        raise ValueError(f"uncompressed file larger than {limit} bytes")
    return out + d.flush()


def parse_file(gz: bytes, stations: set[str]) -> ParsedFile:
    raw = gunzip_capped(gz)
    out = ParsedFile(raw_bytes=len(raw))
    nc = netcdf_file(io.BytesIO(raw), mmap=False)
    try:
        v = nc.variables
        n = int(v["stationId"].shape[0])
        out.records = n
        sids = [_text(r) for r in v["stationId"][:]]
        provider = [_text(r) for r in v["dataProvider"][:]] if "dataProvider" in v else None
        cols = {k: v[k][:] for k in NEEDED if k in v}  # not the ~60 other variables
        has_sky = "skyCvr" in cols and "skyCovLayerBase" in cols
        best: dict[tuple[str, datetime], tuple[float, _Row]] = {}
        for i in (int(k) for k in np.flatnonzero([s in stations for s in sids])):
            sid = sids[i]
            if provider is not None and provider[i] not in PROVIDERS:
                out.skipped_provider += 1
                continue
            obs_s = _num(cols["observationTime"][i])
            if obs_s is None:
                out.bad_time += 1
                continue
            rec_s = _num(cols["receivedTime"][i]) if "receivedTime" in cols else None

            def val(name: str, i: int = i) -> float | None:
                return _num(cols[name][i]) if name in cols else None

            off: dict[str, float] = {}
            temp_c, prec = _temp(val("temperature"), off, "temperature")
            dewpt_c, _dp = _temp(val("dewpoint"), off, "dewpoint")
            qc: dict[str, Any] = {}
            for q in QC_VARS:
                if q not in cols and f"{q}DD" not in cols:
                    continue
                entry: dict[str, Any] = {}
                if f"{q}DD" in cols:
                    entry["dd"] = _char(cols[f"{q}DD"][i])
                for suffix in ("QCA", "QCR"):
                    if f"{q}{suffix}" in cols:
                        entry[suffix.lower()] = int(cols[f"{q}{suffix}"][i])
                qc[q] = entry
            reading = HfReading(
                station_id=sid,
                observed_at=datetime.fromtimestamp(obs_s, UTC),
                received_at=datetime.fromtimestamp(rec_s, UTC) if rec_s is not None else None,
                temp_c=temp_c,
                temp_precision=prec,
                dewpt_c=dewpt_c,
                wind_dir_deg=_grid_int(val("windDir"), Decimal(1), off, "windDir"),
                wind_kt=_grid_int(val("windSpeed"), KT_PER_MS, off, "windSpeed"),
                gust_kt=_grid_int(val("windGust"), KT_PER_MS, off, "windGust"),
                altim_inhg=_grid_dec(val("altimeter"), PA_PER_INHG, Decimal("0.01"), off,
                                     "altimeter", Decimal("0.01")),
                vis_mi=_grid_dec(val("visibility"), M_PER_MI, Decimal("0.0625"), off,
                                 "visibility", Decimal("0.0001")),
                precip_in=_grid_dec(val("precipAccum"), MM_PER_IN, Decimal("0.01"), off,
                                    "precipAccum", Decimal("0.01")),
                qc=qc | ({"off_grid": off} if off else {}),
                raw_message=_text(cols["rawMessage"][i]) or None if "rawMessage" in cols else None,
                sky=_sky(cols["skyCvr"][i], cols["skyCovLayerBase"][i]) if has_sky else None,
                pres_wx=_text(cols["presWx"][i]) or None if "presWx" in cols else None,
            )  # fmt: skip
            key = (sid, reading.observed_at)
            rank = rec_s if rec_s is not None else -1.0
            if key in best:
                out.duplicates += 1
                if rank < best[key][0]:
                    continue
            best[key] = (rank, _Row(reading, len(off)))
        out.readings = [row.reading for _r, row in best.values()]
        out.off_grid = sum(row.off_grid for _r, row in best.values())
    finally:
        nc.close()
    return out


# ---------------------------------------------------------------- remote API


@dataclass(frozen=True)
class RemoteFile:
    name: str
    size_bytes: int
    modified_at: datetime

    @property
    def hour(self) -> datetime:
        m = NAME_RE.match(self.name)
        if m is None:  # parse_listing only builds RemoteFile from matching names
            raise ValueError(self.name)
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H").replace(tzinfo=UTC)


def parse_listing(payload: Any) -> list[RemoteFile]:
    out: list[RemoteFile] = []
    for f in (payload or {}).get("files", []):
        name = str(f.get("name", ""))
        if not NAME_RE.match(name):  # the listing is upstream data: never build a URL from junk
            log.warning("hfmetar: unexpected file name in listing", extra={"source": SOURCE,
                        "file_name": name[:80]})  # fmt: skip
            continue
        out.append(
            RemoteFile(name, int(f["size_bytes"]), as_utc(datetime.fromisoformat(f["modified_at"])))
        )
    return out


def check_base_url(base_url: str) -> str:
    """The token must never travel over plain HTTP (only a loopback address may use it)."""
    u = urlsplit(base_url)
    if u.scheme == "https" or (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost")):
        return base_url.rstrip("/")
    raise ValueError("LDM_API_BASE_URL must be https:// (the bearer token is sent with it)")


@dataclass
class RunMetrics:
    health_ok: bool = False
    backfill: bool = False  # the process's first run: every row it stores is backfill
    files_listed: int = 0
    files_changed: int = 0
    files_processed: int = 0
    files_deferred: int = 0  # changed, but beyond this run's cap (next run)
    files_failed: int = 0
    bytes_downloaded: int = 0
    bytes_uncompressed: int = 0
    records: int = 0
    our_rows: int = 0
    new: int = 0
    revised: int = 0
    qc_changed: int = 0
    unchanged: int = 0
    duplicates: int = 0
    skipped_provider: int = 0
    off_grid: int = 0
    errors: list[str] = field(default_factory=list)


class HfmetarIngest:
    def __init__(
        self,
        client: httpx.Client,
        base_url: str,
        token: str,
        *,
        max_files: int = 6,
        backfill_hours: int = 24,
        stale_minutes: int = 15,
        now: Callable[[], datetime] = utcnow,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not token:
            raise ValueError("MADIS_API_TOKEN is not set")
        self.client = client
        self.base = check_base_url(base_url)
        self._auth = {"Authorization": f"Bearer {token}"}
        self.max_files = max_files
        self.backfill = timedelta(hours=backfill_hours)
        self.stale = timedelta(minutes=stale_minutes)
        self.now = now
        self.sleep = sleep
        self.alerts: dict[str, tuple[datetime, datetime]] = {}  # key → (since, last logged)
        self.live = False  # True after the first run that got a file list: later rows are live
        self.deferred: set[str] = set()  # files left for a later run by the cap: still backfill

    # -- HTTP

    def health(self) -> str | None:
        """None when /health answers 200, else the error."""
        try:
            r = get_with_retry(self.client, f"{self.base}/health", attempts=2, sleep=self.sleep)
        except UpstreamError as exc:
            return str(exc)
        return None if r.status_code == 200 else f"HTTP {r.status_code}"

    def list_files(self) -> list[RemoteFile]:
        r = get_with_retry(self.client, f"{self.base}/api/v1/hfmetar/files", headers=self._auth,
                           sleep=self.sleep)  # fmt: skip
        if r.status_code != 200:
            raise UpstreamError(f"file list: HTTP {r.status_code}")
        return parse_listing(r.json())

    def download(self, f: RemoteFile) -> tuple[bytes, datetime | None]:
        r = get_with_retry(self.client, f"{self.base}/api/v1/hfmetar/{f.name}",
                           headers=self._auth, sleep=self.sleep)  # fmt: skip
        if r.status_code != 200:
            raise UpstreamError(f"{f.name}: HTTP {r.status_code}")
        if len(r.content) > MAX_GZ_BYTES:
            raise UpstreamError(f"{f.name}: {len(r.content)} bytes, larger than expected")
        lm = r.headers.get("Last-Modified")
        try:
            header_mod = as_utc(parsedate_to_datetime(lm)) if lm else None
        except (TypeError, ValueError):
            header_mod = None
        return r.content, header_mod

    # -- alerts

    def _alert(self, key: str, active: bool, message: str, extra: dict[str, Any]) -> None:
        now = self.now()
        if active:
            since, last = self.alerts.get(key, (now, now - ALERT_REPEAT))
            if now - last >= ALERT_REPEAT:
                log.error(f"hfmetar alert: {message}", extra={
                    "source": SOURCE, "alert": key, "since": since.isoformat(), **extra,
                })  # fmt: skip
                last = now
            self.alerts[key] = (since, last)
        elif key in self.alerts:
            since, _ = self.alerts.pop(key)
            log.warning(f"hfmetar alert resolved: {key}", extra={
                "source": SOURCE, "alert": key, "since": since.isoformat(),
                "minutes": round((now - since).total_seconds() / 60, 1),
            })  # fmt: skip

    # -- run

    def run(self, factory: sessionmaker[Session]) -> RunMetrics:
        started = time.perf_counter()
        rss0, _ = rss_mb()
        attempt_at = self.now()
        m = RunMetrics()
        err = self.health()
        m.health_ok = err is None
        self._alert("ldm_health", not m.health_ok, "LDM API /health failing", {"error": err})
        if err is not None:
            with session_scope(factory) as s:
                record_failure(s, SOURCE, attempt_at, f"LDM /health: {err}")
            self._log(m, started, rss0)
            return m
        try:
            files = self.list_files()
        except (UpstreamError, ValueError, KeyError) as exc:
            m.errors.append(f"list: {exc}")
            with session_scope(factory) as s:
                record_failure(s, SOURCE, attempt_at, f"file list: {exc}")
            self._log(m, started, rss0)
            return m
        m.files_listed = len(files)
        with session_scope(factory) as s:
            stations = set(s.scalars(select(Station.id).where(Station.active)))
            known = {
                f.name: (as_utc(f.modified_at), f.size_bytes) for f in s.scalars(select(HfFile))
            }
        cutoff = attempt_at - self.backfill
        changed = sorted(
            (f for f in files
             if f.hour + timedelta(hours=1) > cutoff
             and known.get(f.name) != (f.modified_at, f.size_bytes)),
            key=lambda f: f.name, reverse=True,  # newest hour first: live data before backfill
        )  # fmt: skip
        m.files_changed = len(changed)
        m.files_deferred = max(0, len(changed) - self.max_files)
        m.backfill = not self.live
        self.deferred |= {f.name for f in changed[self.max_files :]}
        for f in changed[: self.max_files]:
            try:
                bf = not self.live or f.name in self.deferred
                self._process(factory, f, stations, m, backfill=bf)
                self.deferred.discard(f.name)
            except Exception as exc:
                m.files_failed += 1
                m.errors.append(f"{f.name}: {type(exc).__name__}: {exc}"[:300])
                log.exception("hfmetar file failed", extra={"source": SOURCE, "file_name": f.name})
        with session_scope(factory) as s:
            last_new = last_ingested_at(s)
            latest_obs = s.scalar(select(func.max(HfObservation.observed_at)))
            record_success(
                s, SOURCE, attempt_at,
                last_item_time=as_utc(latest_obs) if latest_obs else None,
                notes=(f"files {m.files_processed}/{m.files_changed} new={m.new} "
                       f"revised={m.revised} qc={m.qc_changed}"),
            )  # fmt: skip
            if m.errors:
                record_failure(s, SOURCE, self.now(), "; ".join(m.errors)[:2000])
        self.live = True
        stale = last_new is None or self.now() - last_new > self.stale
        self._alert("no_new_readings", stale, "no new 5-minute readings while LDM /health is ok",
                    {"last_ingested_at": last_new.isoformat() if last_new else None,
                     "stale_minutes": self.stale.total_seconds() / 60})  # fmt: skip
        self._log(m, started, rss0)
        return m

    def _process(
        self,
        factory: sessionmaker[Session],
        f: RemoteFile,
        stations: set[str],
        m: RunMetrics,
        *,
        backfill: bool,
    ) -> None:
        gz, header_mod = self.download(f)
        fetched_at = self.now()
        m.bytes_downloaded += len(gz)
        parsed = parse_file(gz, stations)
        del gz
        m.bytes_uncompressed += parsed.raw_bytes
        m.records += parsed.records
        m.our_rows += len(parsed.readings)
        m.duplicates += parsed.duplicates
        m.skipped_provider += parsed.skipped_provider
        m.off_grid += parsed.off_grid
        # the content we got may be a newer version than the listing said
        file_mod = max(f.modified_at, header_mod) if header_mod else f.modified_at
        with session_scope(factory) as s:
            res = upsert_readings(
                s, parsed.readings, source_file=f.name, file_modified_at=file_mod,
                fetched_at=fetched_at, now=self.now(), backfill=backfill,
            )  # fmt: skip
            row = s.get(HfFile, f.name) or HfFile(name=f.name)
            row.modified_at = f.modified_at
            row.size_bytes = f.size_bytes
            row.processed_at = self.now()
            row.records = parsed.records
            row.our_rows = len(parsed.readings)
            s.add(row)
        m.files_processed += 1
        m.new += res.new
        m.revised += res.revised
        m.qc_changed += res.qc_changed
        m.unchanged += res.unchanged

    def _log(self, m: RunMetrics, started: float, rss0: float | None) -> None:
        rss1, peak = rss_mb()
        log.info(
            "hfmetar ingest",
            extra={
                "source": SOURCE,
                "health_ok": m.health_ok,
                "backfill_run": m.backfill,
                "files_listed": m.files_listed,
                "files_changed": m.files_changed,
                "files_processed": m.files_processed,
                "files_deferred": m.files_deferred,
                "files_failed": m.files_failed,
                "bytes_downloaded": m.bytes_downloaded,
                "bytes_uncompressed": m.bytes_uncompressed,
                "records": m.records,
                "our_rows": m.our_rows,
                "count_new": m.new,
                "count_revised": m.revised,
                "count_qc_changed": m.qc_changed,
                "count_unchanged": m.unchanged,
                "duplicates_in_file": m.duplicates,
                "skipped_provider": m.skipped_provider,
                "off_grid": m.off_grid,
                "errors": m.errors[:5],
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "rss_start_mb": rss0,
                "rss_end_mb": rss1,
                "process_peak_rss_mb": peak,
            },
        )
