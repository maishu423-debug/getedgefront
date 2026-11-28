"""Test data for the end-to-end tests (v2 Phase 10): METARs and 5-minute readings for the last
26 hours, ending a few minutes before "now". **Never for production**: refused when APP_ENV=prod,
and every row is marked (`source = "e2e-seed"`, file names `e2e.*`).

    uv run python -m edgefront_core.e2e_seed --yes-this-is-a-test-database

The values are made up but internally consistent with the real feeds (Phase 9 findings): each
station has a whole-°F "reading" curve; the METAR T-group is that reading in tenths °C (nearest),
the METAR body is the NWS half-up of the T-group, and the 5-minute value is the nearest whole °C
of the reading. Cases the UI tests need:

- KNYC and KBKF: no 5-minute data (not in the real feed either)
- KSEA: 5-minute data stops 45 minutes before now (stale)
- KDFW: one questioned (QC "Q") spike 15 minutes before the newest reading (so inside today's
  climate day), left out of the 5-minute high
- KBOS: a 40-minute gap three hours ago
- every station: a 5-minute peak 2 °F above the curve between two hourly METARs
"""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from edgefront_core.db import get_engine, make_sessionmaker, session_scope
from edgefront_core.hf_store import SOURCE as HF_SOURCE
from edgefront_core.hf_store import HfReading, upsert_readings
from edgefront_core.metar_ingest import SOURCE as METAR_SOURCE
from edgefront_core.metar_ingest import store_reports, sync_high_events
from edgefront_core.models import HfFile, HfObservation, MetarReport, Station
from edgefront_core.settings import get_settings
from edgefront_core.source_health import record_success
from edgefront_core.units import f_to_c, f_to_c10

# Station positions as the enrichment step stores them in production (3 decimals), so the map has
# coordinates in a test database that was only seeded from the registry.
COORDS: dict[str, tuple[float, float]] = {
    "KNYC": (40.783, -73.967),
    "KLGA": (40.779, -73.88),
    "KBOS": (42.361, -71.011),
    "KPHL": (39.873, -75.227),
    "KDCA": (38.848, -77.034),
    "KATL": (33.64, -84.427),
    "KCLT": (35.208, -80.961),
    "KMIA": (25.791, -80.316),
    "KJAX": (30.495, -81.694),
    "KDTW": (42.231, -83.331),
    "KMDW": (41.784, -87.755),
    "KORD": (41.98, -87.904),
    "KMSP": (44.883, -93.229),
    "KBNA": (36.119, -86.689),
    "KOKC": (35.389, -97.6),
    "KDFW": (32.897, -97.022),
    "KDAL": (32.854, -96.855),
    "KAUS": (30.183, -97.68),
    "KSAT": (29.533, -98.464),
    "KHOU": (29.637, -95.282),
    "KSDF": (38.174, -85.737),
    "KDEN": (39.847, -104.656),
    "KBKF": (39.713, -104.758),
    "KPHX": (33.428, -112.003),
    "KLAX": (33.938, -118.389),
    "KSFO": (37.62, -122.366),
    "KSEA": (47.445, -122.314),
    "KLAS": (36.072, -115.163),
}
NOT_IN_FEED = frozenset({"KNYC", "KBKF"})
STALE = "KSEA"
QC_SPIKE = "KDFW"
GAP = "KBOS"
HOURS = 26
MARK = "e2e-seed"


def _base_f(sid: str) -> int:
    return 40 + int(hashlib.sha256(sid.encode()).hexdigest(), 16) % 30  # 40..69 °F


def reading_f(sid: str, tz: str, at: datetime) -> int:
    """The station's whole-°F reading: a daily curve peaking mid-afternoon local time."""
    local = at.astimezone(ZoneInfo(tz))
    h = local.hour + local.minute / 60
    v = _base_f(sid) + 9 * math.cos(2 * math.pi * (h - 15) / 24)
    if 13.3 <= h < 13.55:  # a short peak between two hourly METARs (:53 → :53)
        v += 2
    return math.floor(v + 0.5)


def _tgroup(c10: int) -> str:
    return f"{1 if c10 < 0 else 0}{abs(c10):03d}"


def _body(c10: int) -> str:
    whole = (c10 + 5) // 10  # NWS half-up of the tenths (the METAR body)
    return f"M{abs(whole):02d}" if whole < 0 else f"{whole:02d}"


def metar_item(st: Station, at: datetime) -> dict[str, object]:
    f = reading_f(st.id, st.tz, at)
    c10 = f_to_c10(f)
    d10 = f_to_c10(f - 14)
    raw = (
        f"METAR {st.id} {at:%d%H%M}Z AUTO 18008KT 10SM CLR {_body(c10)}/{_body(d10)} A3007 "
        f"RMK AO2 T{_tgroup(c10)}{_tgroup(d10)}"
    )
    return {
        "icaoId": st.id,
        "obsTime": int(at.timestamp()),
        "receiptTime": (at + timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
        "reportTime": at.isoformat().replace("+00:00", "Z"),
        "metarType": "METAR",
        "rawOb": raw,
    }


def hf_reading(st: Station, at: datetime, spike_at: datetime | None = None) -> HfReading:
    f = reading_f(st.id, st.tz, at)
    dd = "V"
    c = f_to_c(f)
    if st.id == QC_SPIKE and at == spike_at:
        c += 6  # a questioned spike: stored with its flag, left out of the high
        dd = "Q"
    return HfReading(
        st.id,
        at,
        received_at=at + timedelta(seconds=140),
        temp_c=Decimal(c),
        temp_precision="whole_c",
        dewpt_c=Decimal(f_to_c(f - 14)),
        wind_dir_deg=180,
        wind_kt=8,
        gust_kt=None,
        altim_inhg=Decimal("30.07"),
        vis_mi=Decimal(10),
        precip_in=Decimal(0),
        qc={"temperature": {"dd": dd, "qca": 123, "qcr": 0 if dd == "V" else 16}},
    )


def seed_e2e(now: datetime) -> dict[str, int]:
    factory = make_sessionmaker(get_engine())
    end = now.replace(second=0, microsecond=0)
    end -= timedelta(minutes=end.minute % 5 + 5)  # the newest 5-minute reading: 5-9 min ago
    start = end - timedelta(hours=HOURS)
    out = {"metar": 0, "hf": 0}
    with session_scope(factory) as s:
        stations = list(s.scalars(select(Station).where(Station.active).order_by(Station.id)))
        for st in stations:
            if st.lat is None and st.id in COORDS:
                st.lat, st.lon = COORDS[st.id]
        s.execute(delete(HfObservation))
        s.execute(delete(HfFile))
        s.execute(delete(MetarReport).where(MetarReport.source == MARK))
    for st in stations:
        items = []
        t = start.replace(minute=53)
        while t <= now - timedelta(minutes=3):
            if t >= start:
                items.append(metar_item(st, t))
            t += timedelta(hours=1)
        with session_scope(factory) as s:
            res = store_reports(s, items, now)
            s.flush()
            for row in s.scalars(
                select(MetarReport).where(
                    MetarReport.station_id == st.id, MetarReport.fetched_at == now
                )
            ):
                row.source = MARK  # only the rows written here
            out["metar"] += res.new
            for _sid, day in sorted(res.affected_days):
                sync_high_events(s, st, day)
        if st.id in NOT_IN_FEED:
            continue
        last = end - timedelta(minutes=45) if st.id == STALE else end
        readings = []
        t = start
        while t <= last:
            gap_from = end - timedelta(hours=3)
            if not (st.id == GAP and gap_from <= t < gap_from + timedelta(minutes=40)):
                readings.append(hf_reading(st, t, spike_at=end - timedelta(minutes=15)))
            t += timedelta(minutes=5)
        with session_scope(factory) as s:
            for hour_start in sorted({r.observed_at.replace(minute=0) for r in readings}):
                batch = [r for r in readings if r.observed_at.replace(minute=0) == hour_start]
                mod = max(r.observed_at for r in batch) + timedelta(minutes=12)
                upsert_readings(
                    s, batch, source_file=f"e2e.{hour_start:%Y%m%d_%H}00.gz",
                    file_modified_at=mod, fetched_at=mod + timedelta(seconds=40),
                    now=mod + timedelta(seconds=41),
                )  # fmt: skip
            out["hf"] += len(readings)
    with session_scope(factory) as s:
        s.add(
            HfFile(
                name=f"e2e.{end:%Y%m%d_%H}00.gz",
                modified_at=end + timedelta(minutes=12),
                size_bytes=1,
                processed_at=now,
                records=out["hf"],
                our_rows=out["hf"],
            )
        )
        record_success(s, METAR_SOURCE, now, last_item_time=now - timedelta(minutes=3))
        record_success(s, HF_SOURCE, now, last_item_time=end)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--yes-this-is-a-test-database", action="store_true", required=True)
    p.parse_args(argv)
    if get_settings().app_env == "prod":
        print("refused: APP_ENV=prod", file=sys.stderr)
        return 2
    out = seed_e2e(datetime.now(UTC))
    print(f"e2e seed: {out['metar']} METARs, {out['hf']} 5-minute readings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
