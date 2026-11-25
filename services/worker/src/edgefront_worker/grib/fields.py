"""Decode single GRIB2 messages (eccodes) and pick station grid points (CONTEXT §4.4).

Space rule (owner, Phase 5): the **nearest land grid point** (land fraction >= 0.5) to the
station; no interpolation, no lapse-rate or bias adjustment. The chosen point's lat/lon,
great-circle distance, land fraction and model orography height are stored with the run.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import eccodes
import numpy as np
from numpy.typing import NDArray

LAND_THRESHOLD = 0.5
G = 9.80665  # m s-2, geopotential → height


@dataclass(frozen=True)
class Grid:
    """A regular lat/lon grid as described by the message (global or regional)."""

    lat0: float
    lon0: float
    dlat: float  # signed: negative when rows run north → south
    dlon: float
    ni: int
    nj: int
    global_lon: bool

    def lat(self, j: int) -> float:
        return self.lat0 + j * self.dlat

    def lon(self, i: int) -> float:
        lon = self.lon0 + i * self.dlon
        return ((lon + 180.0) % 360.0) - 180.0

    def nearest_ij(self, lat: float, lon: float) -> tuple[int, int]:
        j = round((lat - self.lat0) / self.dlat)
        di = ((lon - self.lon0) % 360.0) / self.dlon
        i = round(di)
        if self.global_lon:
            i %= self.ni
        return j, i

    def contains(self, j: int, i: int) -> bool:
        return 0 <= j < self.nj and 0 <= i < self.ni


@dataclass
class Field:
    short_name: str
    units: str
    data_date: int
    data_time: int
    step: str
    grid: Grid
    values: NDArray[np.float64]  # (nj, ni)

    def at(self, j: int, i: int) -> float | None:
        v = float(self.values[j, i])
        return None if math.isnan(v) else v


class GribError(ValueError):
    pass


def decode(message: bytes) -> Field:
    h = eccodes.codes_new_from_message(message)
    try:
        if eccodes.codes_get(h, "gridType") != "regular_ll":
            raise GribError(f"unsupported grid {eccodes.codes_get(h, 'gridType')}")
        ni, nj = eccodes.codes_get(h, "Ni"), eccodes.codes_get(h, "Nj")
        dlat = eccodes.codes_get(h, "jDirectionIncrementInDegrees")
        dlon = eccodes.codes_get(h, "iDirectionIncrementInDegrees")
        if eccodes.codes_get(h, "jScansPositively") == 0:
            dlat = -dlat
        if eccodes.codes_get(h, "iScansNegatively") == 1:
            dlon = -dlon
        lon0 = eccodes.codes_get(h, "longitudeOfFirstGridPointInDegrees")
        grid = Grid(
            lat0=eccodes.codes_get(h, "latitudeOfFirstGridPointInDegrees"),
            lon0=lon0,
            dlat=dlat,
            dlon=dlon,
            ni=ni,
            nj=nj,
            global_lon=abs(ni * abs(dlon) - 360.0) < 1e-6,
        )
        values = np.asarray(eccodes.codes_get_values(h), dtype=np.float64)
        if eccodes.codes_get(h, "numberOfMissing") > 0:
            values[values == eccodes.codes_get(h, "missingValue")] = np.nan
        if values.size != ni * nj:
            raise GribError(f"{values.size} values for a {ni}x{nj} grid")
        return Field(
            short_name=eccodes.codes_get(h, "shortName"),
            units=eccodes.codes_get(h, "units"),
            data_date=eccodes.codes_get(h, "dataDate"),
            data_time=eccodes.codes_get(h, "dataTime"),
            step=str(eccodes.codes_get(h, "stepRange")),
            grid=grid,
            values=values.reshape(nj, ni),
        )
    finally:
        eccodes.codes_release(h)


def km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class StationPoint:
    j: int
    i: int
    lat: float
    lon: float
    distance_km: float
    land_fraction: float
    is_land: bool


def nearest_land_point(lsm: Field, lat: float, lon: float, *, max_radius: int = 4) -> StationPoint:
    """Nearest grid point with land fraction >= 0.5, searching outward ring by ring.

    The nearest point by distance is taken among all land points within `max_radius` cells
    (a ring may hold a farther point than the next ring, so the whole box is ranked). When no
    land point exists in the box, the nearest point is returned with is_land=False.
    """
    g = lsm.grid
    j0, i0 = g.nearest_ij(lat, lon)
    best: StationPoint | None = None
    nearest: StationPoint | None = None
    for dj in range(-max_radius, max_radius + 1):
        for di in range(-max_radius, max_radius + 1):
            j, i = j0 + dj, i0 + di
            if g.global_lon:
                i %= g.ni
            if not g.contains(j, i):
                continue
            frac = lsm.at(j, i)
            if frac is None:
                continue
            plat, plon = g.lat(j), g.lon(i)
            d = km_between(lat, lon, plat, plon)
            p = StationPoint(j, i, plat, plon, d, frac, frac >= LAND_THRESHOLD)
            if nearest is None or d < nearest.distance_km:
                nearest = p
            if p.is_land and (best is None or d < best.distance_km):
                best = p
    chosen = best or nearest
    if chosen is None:
        raise GribError(f"station {lat},{lon} is outside the grid")
    return chosen


def height_m(orog: Field, p: StationPoint) -> float | None:
    """Model surface height at the point: GFS HGT (gpm) or ECMWF z (m2 s-2)."""
    v = orog.at(p.j, p.i)
    if v is None:
        return None
    return round(v / G, 1) if orog.units.startswith("m**2") else round(v, 1)
