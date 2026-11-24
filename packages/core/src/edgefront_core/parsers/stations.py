"""Station metadata parsers: aviationweather stationinfo, NWS /stations, NWS /points,
plus the product headers used to discover dsm_location and pfm_point."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------- aviationweather.gov


@dataclass(frozen=True)
class AwcStation:
    icao: str
    site: str | None
    lat: float | None
    lon: float | None
    elev_m: float | None
    state: str | None


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def parse_awc_stationinfo(data: Any) -> dict[str, AwcStation]:
    """`/api/data/stationinfo?format=json` → {ICAO: AwcStation}. `elev` is metres."""
    if not isinstance(data, list):
        raise ValueError("stationinfo: expected a JSON list")
    out: dict[str, AwcStation] = {}
    for item in data:
        icao = item.get("icaoId")
        if not isinstance(icao, str):
            continue
        out[icao] = AwcStation(
            icao=icao,
            site=item.get("site") or None,
            lat=_num(item.get("lat")),
            lon=_num(item.get("lon")),
            elev_m=_num(item.get("elev")),
            state=item.get("state") or None,
        )
    return out


# ---------------------------------------------------------------- api.weather.gov


@dataclass(frozen=True)
class NwsStation:
    icao: str
    name: str | None
    lat: float | None
    lon: float | None
    elevation_m: float | None
    tz: str | None


def parse_nws_station(doc: dict[str, Any]) -> NwsStation:
    """`/stations/{id}` (GeoJSON). Coordinates are [lon, lat]."""
    props = doc["properties"]
    coords = (doc.get("geometry") or {}).get("coordinates") or [None, None]
    elev = props.get("elevation") or {}
    if elev.get("unitCode") not in (None, "wmoUnit:m"):
        raise ValueError(f"unexpected elevation unit {elev.get('unitCode')}")
    return NwsStation(
        icao=props["stationIdentifier"],
        name=props.get("name") or None,
        lat=_num(coords[1]),
        lon=_num(coords[0]),
        elevation_m=_num(elev.get("value")),
        tz=props.get("timeZone") or None,
    )


@dataclass(frozen=True)
class NwsPoint:
    office: str  # gridId: the office used in /gridpoints/{office}/{x},{y}
    cwa: str | None
    grid_x: int
    grid_y: int
    tz: str | None


def parse_nws_points(doc: dict[str, Any]) -> NwsPoint:
    props = doc["properties"]
    return NwsPoint(
        office=props["gridId"],
        cwa=props.get("cwa"),
        grid_x=int(props["gridX"]),
        grid_y=int(props["gridY"]),
        tz=props.get("timeZone"),
    )


def points_url(lat: float, lon: float) -> str:
    # NWS redirects requests with more than 4 decimals; send 4.
    return f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"


# ---------------------------------------------------------------- products: DSM / PFM

_DSM_HEAD = re.compile(r"^(K[A-Z0-9]{3}) DS\b")


def dsm_station_id(product_text: str) -> str | None:
    """ICAO of the station a DSM product reports on (first `KXXX DS ...` line), or None."""
    for line in product_text.splitlines():
        m = _DSM_HEAD.match(line.strip())
        if m:
            return m.group(1)
    return None


@dataclass(frozen=True)
class PfmPoint:
    ugc: str  # zone line, e.g. "NYZ072-242100-" (not unique within a product)
    name: str  # point name line, e.g. "Central Park-New York NY"
    lat: float
    lon: float
    elev_ft: int | None


# Offices differ: "40.78N  73.97W Elev. 16 ft" (OKX) vs
# "36.07N 115.16W Elev. (Average Over 2.5KM Grid Box): 2181 ft" (VEF).
_PFM_LATLON = re.compile(
    r"^(\d{1,2}\.\d+)([NS])\s+(\d{1,3}\.\d+)([EW])"
    r"(?:\s+Elev\.(?:\s*\([^)]*\):)?\s*(-?\d+)\s*ft)?\s*$"
)
_UGC = re.compile(r"^[A-Z]{2}[CZ]\d{3}[->]")


def parse_pfm_points(product_text: str) -> list[PfmPoint]:
    """Point blocks of a PFM: a UGC line, a name line, then `40.78N  73.97W Elev. 16 ft`."""
    lines = [line.rstrip() for line in product_text.splitlines()]
    points: list[PfmPoint] = []
    for i, line in enumerate(lines):
        m = _PFM_LATLON.match(line.strip())
        if not m or i < 2:
            continue
        ugc, name = lines[i - 2].strip(), lines[i - 1].strip()
        if not _UGC.match(ugc) or not name:
            continue
        lat = float(m.group(1)) * (1 if m.group(2) == "N" else -1)
        lon = float(m.group(3)) * (1 if m.group(4) == "E" else -1)
        points.append(
            PfmPoint(
                ugc=ugc,
                name=name,
                lat=lat,
                lon=lon,
                elev_ft=int(m.group(5)) if m.group(5) else None,
            )
        )
    return points


def km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class PfmMatch:
    point: PfmPoint | None
    distance_km: float | None
    reason: str


def match_pfm_point(
    points: list[PfmPoint], lat: float, lon: float, max_km: float = 3.0
) -> PfmMatch:
    """Clear evidence only: nearest point within `max_km` (PFM coords are rounded to 0.01°,
    ~1 km) and no other point within twice that distance. Otherwise no match, with a reason."""
    if not points:
        return PfmMatch(None, None, "no PFM points")
    ranked = sorted(points, key=lambda p: km_between(lat, lon, p.lat, p.lon))
    best = ranked[0]
    d1 = km_between(lat, lon, best.lat, best.lon)
    if d1 > max_km:
        return PfmMatch(None, d1, f"nearest point '{best.name}' is {d1:.1f} km away")
    if len(ranked) > 1:
        d2 = km_between(lat, lon, ranked[1].lat, ranked[1].lon)
        if d2 < max(2 * d1, 1.0):
            return PfmMatch(
                None, d1, f"ambiguous: '{best.name}' {d1:.1f} km, '{ranked[1].name}' {d2:.1f} km"
            )
    return PfmMatch(best, d1, "ok")
