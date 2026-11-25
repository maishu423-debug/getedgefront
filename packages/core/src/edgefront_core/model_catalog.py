"""The v1 model launch set (CONTEXT.md §4.4) and what the API/UI needs to label each one."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str
    group: str  # global | ai | statistical | nws
    producer: str
    colour_token: str  # CSS token name in apps/web globals.css (--color-model-*)
    kind: str  # gridded | station_text | point_text
    cycle_interval: timedelta  # how often a new run is expected; stale after 2x
    native_step_hours: tuple[int, ...]  # steps the product uses (for line breaks)
    variables: tuple[str, ...]  # what the product carries (others get "no {variable}")
    licence: str | None = None

    @property
    def source_key(self) -> str:
        """`source_health` key and /status entry."""
        return f"model_{self.id}"


MODELS: tuple[ModelInfo, ...] = (
    ModelInfo(
        "ifs", "IFS", "global", "ECMWF", "model-ifs", "gridded", timedelta(hours=6), (3,),
        ("temp", "dewpt", "wind", "cloud", "rh"), "CC BY 4.0",
    ),
    ModelInfo(
        "gfs", "GFS", "global", "NOAA/NCEP", "model-gfs", "gridded", timedelta(hours=6), (1,),
        ("temp", "dewpt", "wind", "cloud", "rh"),
    ),
    ModelInfo(
        "aifs", "AIFS", "ai", "ECMWF", "model-aifs", "gridded", timedelta(hours=6), (6,),
        ("temp", "dewpt", "wind", "cloud", "rh"), "CC BY 4.0",
    ),
    ModelInfo(
        "gfs_mos", "GFS-MOS", "statistical", "NWS Meteorological Development Laboratory",
        "model-gfsmos", "station_text", timedelta(hours=6), (3, 6),
        ("temp", "dewpt", "wind", "cloud", "rh"),
    ),
    ModelInfo(
        "nbm", "NBM", "statistical", "NWS National Blend of Models", "model-nbm",
        "station_text", timedelta(hours=1), (1, 3), ("temp", "dewpt", "wind", "cloud", "rh"),
    ),
    ModelInfo(
        "lamp", "LAMP", "statistical", "NWS Meteorological Development Laboratory",
        "model-lamp", "station_text", timedelta(hours=1), (1,),
        ("temp", "dewpt", "wind", "cloud", "rh"),
    ),
    ModelInfo(
        "pfm", "PFM", "nws", "NWS forecast office (Point Forecast Matrix)", "model-pfm",
        "point_text", timedelta(hours=12), (3,), ("temp", "dewpt", "wind", "cloud", "rh"),
    ),
)  # fmt: skip

BY_ID = {m.id: m for m in MODELS}
VARIABLES = ("temp", "dewpt", "wind", "cloud", "rh")
RETAIN_RUNS = 4  # latest runs kept per model (per issuer for PFM) — §9
