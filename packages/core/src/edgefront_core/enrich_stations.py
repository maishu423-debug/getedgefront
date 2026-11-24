"""Fill station metadata from upstream and discover dsm_location / pfm_point (CONTEXT.md §5).

    python -m edgefront_core.enrich_stations [--no-discover]

Writes lat, lon, elevation_m, official_name, nws_office, grid_x, grid_y, enriched_at,
enrichment_source. dsm_location / pfm_point are written only when the evidence is clear AND
the field is empty; anything doubtful is printed as a flag for the owner. Idempotent.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from edgefront_core.db import get_engine, make_sessionmaker, session_scope
from edgefront_core.http import get_with_retry, make_client
from edgefront_core.models import Station
from edgefront_core.parsers.stations import (
    PfmPoint,
    dsm_station_id,
    km_between,
    match_pfm_point,
    parse_awc_stationinfo,
    parse_nws_points,
    parse_nws_station,
    parse_pfm_points,
    points_url,
)
from edgefront_core.timeutil import utcnow

AWC_STATIONINFO = "https://aviationweather.gov/api/data/stationinfo"
NWS = "https://api.weather.gov"
LD = {"Accept": "application/ld+json"}
GEO = {"Accept": "application/geo+json"}
DSM_MAX_AGE = timedelta(days=7)
SOURCE_NOTE = (
    "aviationweather.gov stationinfo; api.weather.gov /stations, /points; "
    "api.weather.gov products DSM/PFM (discovery)"
)


@dataclass
class StationReport:
    id: str
    lat: float | None = None
    lon: float | None = None
    elevation_m: float | None = None
    official_name: str | None = None
    office: str | None = None
    grid: str | None = None
    tz_ok: bool | None = None
    dsm: str | None = None
    dsm_note: str = ""
    pfm: str | None = None
    pfm_note: str = ""
    flags: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)


class Enricher:
    def __init__(
        self,
        client: httpx.Client,
        *,
        now: Callable[[], datetime] = utcnow,
        pause: Callable[[], None] = lambda: time.sleep(0.25),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.now = now
        self.pause = pause
        self.sleep = sleep
        self._pfm_cache: dict[str, tuple[list[PfmPoint], str]] = {}

    def _get(self, url: str, **kw: Any) -> httpx.Response:
        self.pause()
        return get_with_retry(self.client, url, sleep=self.sleep, **kw)

    def _json(self, url: str, headers: dict[str, str]) -> Any | None:
        r = self._get(url, headers=headers)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------ discovery

    def discover_dsm(self, st: Station, rep: StationReport) -> None:
        candidate = st.dsm_location or st.id[1:]
        listing = self._json(f"{NWS}/products/types/DSM/locations/{candidate}", LD) or {}
        graph = listing.get("@graph") or []
        if not graph:
            rep.dsm_note = f"no DSM products under location {candidate}"
        else:
            latest = graph[0]
            prod = self._json(f"{NWS}/products/{latest['id']}", LD) or {}
            named = dsm_station_id(prod.get("productText") or "")
            issued = datetime.fromisoformat(latest["issuanceTime"])
            if named != st.id:
                rep.dsm_note = f"latest {candidate} DSM names {named}, not {st.id}"
            elif self.now() - issued > DSM_MAX_AGE:
                rep.dsm_note = f"latest {candidate} DSM is stale ({issued:%Y-%m-%d})"
            else:
                rep.dsm = candidate
                rep.dsm_note = f"confirmed: {candidate} DSM issued {issued:%Y-%m-%dT%H:%MZ}"
        if rep.dsm and st.dsm_location is None:
            st.dsm_location = rep.dsm
            rep.changed.append("dsm_location")
        elif st.dsm_location and rep.dsm != st.dsm_location:
            rep.flags.append(f"stored dsm_location {st.dsm_location} not confirmed")

    def _pfm_points(self, office: str) -> tuple[list[PfmPoint], str]:
        if office not in self._pfm_cache:
            listing = self._json(f"{NWS}/products/types/PFM/locations/{office}", LD) or {}
            graph = listing.get("@graph") or []
            if not graph:
                self._pfm_cache[office] = ([], f"no PFM products for office {office}")
            else:
                prod = self._json(f"{NWS}/products/{graph[0]['id']}", LD) or {}
                pts = parse_pfm_points(prod.get("productText") or "")
                self._pfm_cache[office] = (pts, f"PFM{office} {graph[0]['issuanceTime'][:16]}Z")
        return self._pfm_cache[office]

    def discover_pfm(self, st: Station, office: str, rep: StationReport) -> None:
        if st.lat is None or st.lon is None:
            rep.pfm_note = "no coordinates"
            return
        pts, src = self._pfm_points(office)
        m = match_pfm_point(pts, st.lat, st.lon)
        if m.point is None:
            rep.pfm_note = f"{m.reason} ({src})" if pts else src
        else:
            rep.pfm = m.point.name
            rep.pfm_note = f"confirmed: {m.distance_km:.1f} km from station ({src})"
        if rep.pfm and st.pfm_point is None:
            st.pfm_point = rep.pfm
            rep.changed.append("pfm_point")
        elif st.pfm_point and rep.pfm != st.pfm_point:
            rep.flags.append(f"stored pfm_point '{st.pfm_point}' not confirmed")

    # ------------------------------------------------------------ main pass

    def run(self, session: Session, discover: bool = True) -> list[StationReport]:
        stations = list(session.scalars(select(Station).where(Station.active).order_by(Station.id)))
        if not stations:
            return []
        r = self._get(
            AWC_STATIONINFO,
            params={"ids": ",".join(s.id for s in stations), "format": "json"},
        )
        r.raise_for_status()
        awc = parse_awc_stationinfo(r.json())

        reports: list[StationReport] = []
        for st in stations:
            rep = StationReport(id=st.id)
            reports.append(rep)
            a = awc.get(st.id)
            if a is None:
                rep.flags.append("not in aviationweather stationinfo")
            elif a.state and a.state != st.state:
                rep.flags.append(f"state: yaml {st.state}, aviationweather {a.state}")

            doc = self._json(f"{NWS}/stations/{st.id}", GEO)
            ns = parse_nws_station(doc) if doc else None
            if ns is None:
                rep.flags.append("not found at api.weather.gov /stations")

            lat = ns.lat if ns and ns.lat is not None else (a.lat if a else None)
            lon = ns.lon if ns and ns.lon is not None else (a.lon if a else None)
            elev = (
                ns.elevation_m if ns and ns.elevation_m is not None else (a.elev_m if a else None)
            )
            name = (ns.name if ns else None) or (a.site if a else None)
            if ns and a and None not in (ns.lat, ns.lon, a.lat, a.lon):
                d = km_between(ns.lat, ns.lon, a.lat, a.lon)  # type: ignore[arg-type]
                if d > 1.0:
                    rep.flags.append(f"NWS vs aviationweather position differ by {d:.1f} km")
            if ns and ns.tz:
                rep.tz_ok = ns.tz == st.tz
                if not rep.tz_ok:
                    rep.flags.append(f"tz: yaml {st.tz}, NWS {ns.tz}")

            values: dict[str, object] = {}
            if lat is not None and lon is not None:
                values.update(lat=round(lat, 5), lon=round(lon, 5))
            if elev is not None:
                values["elevation_m"] = round(elev, 1)
            if name:
                values["official_name"] = name

            office: str | None = None
            if lat is not None and lon is not None:
                pdoc = self._json(points_url(lat, lon), GEO)
                if pdoc is None:
                    rep.flags.append("/points returned 404")
                else:
                    pt = parse_nws_points(pdoc)
                    office = pt.office
                    values.update(nws_office=pt.office, grid_x=pt.grid_x, grid_y=pt.grid_y)
                    if pt.cwa and pt.cwa != pt.office:
                        rep.flags.append(f"/points gridId {pt.office} != cwa {pt.cwa}")

            for k, v in values.items():
                if getattr(st, k) != v:
                    setattr(st, k, v)
                    rep.changed.append(k)
            if rep.changed:
                st.enriched_at = self.now()
                st.enrichment_source = SOURCE_NOTE

            if discover:
                self.discover_dsm(st, rep)
                if office:
                    self.discover_pfm(st, office, rep)
                else:
                    rep.pfm_note = "no office"

            rep.lat, rep.lon, rep.elevation_m = st.lat, st.lon, st.elevation_m
            rep.official_name, rep.office = st.official_name, st.nws_office
            rep.grid = f"{st.grid_x},{st.grid_y}" if st.grid_x is not None else None
            for f_name in ("lat", "lon", "nws_office", "grid_x", "grid_y"):
                if getattr(st, f_name) is None:
                    rep.flags.append(f"MISSING {f_name}")
            session.flush()
        return reports


def _fmt(v: object) -> str:
    return "—" if v is None else str(v)


def print_report(reports: list[StationReport], out: Any = sys.stdout) -> None:
    hdr = (
        f"{'ID':5} {'LAT':>9} {'LON':>10} {'ELEV m':>7} {'OFF':4} {'GRID':8} {'TZ':3} {'DSM':4} PFM"
    )
    out.write(hdr + "\n" + "-" * len(hdr) + "\n")
    for r in reports:
        tz = "ok" if r.tz_ok else ("?" if r.tz_ok is None else "BAD")
        out.write(
            f"{r.id:5} {_fmt(r.lat):>9} {_fmt(r.lon):>10} {_fmt(r.elevation_m):>7} "
            f"{_fmt(r.office):4} {_fmt(r.grid):8} {tz:3} {_fmt(r.dsm):4} {_fmt(r.pfm)}\n"
        )
    out.write("\nDetails\n")
    for r in reports:
        out.write(f"{r.id}: {_fmt(r.official_name)}\n")
        out.write(f"    DSM: {r.dsm_note or '—'}\n    PFM: {r.pfm_note or '—'}\n")
        if r.changed:
            out.write(f"    updated: {', '.join(r.changed)}\n")
        for f in r.flags:
            out.write(f"    FLAG: {f}\n")
    missing = [r.id for r in reports if any(f.startswith("MISSING") for f in r.flags)]
    out.write(
        f"\n{len(reports)} stations · complete: {len(reports) - len(missing)} · "
        f"missing fields: {missing or 'none'} · "
        f"dsm_location: {sum(1 for r in reports if r.dsm)} · "
        f"pfm_point: {sum(1 for r in reports if r.pfm)}\n"
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--no-discover", action="store_true", help="skip DSM/PFM discovery")
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    factory = make_sessionmaker(get_engine())
    with make_client() as client, session_scope(factory) as s:
        reports = Enricher(client).run(s, discover=not a.no_discover)
    print_report(reports)


if __name__ == "__main__":
    main()
