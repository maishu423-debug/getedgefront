"""Load and validate data/stations.yaml (CONTEXT.md §5)."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from edgefront_core.models import MarketKind, Venue

DEFAULT_PATH = Path("data/stations.yaml")


class VenueEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    venue: Venue
    kind: MarketKind
    market: str | None = None
    settlement_source: str | None = None
    rules_url: str | None = None
    verified: bool = False
    verified_at: datetime | None = None

    @model_validator(mode="after")
    def _verified_needs_evidence(self) -> VenueEntry:
        if self.verified and (self.rules_url is None or self.verified_at is None):
            raise ValueError("verified: true requires rules_url and verified_at")
        return self


class StationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^K[A-Z0-9]{3}$")
    name: str
    city: str
    state: str = Field(pattern=r"^[A-Z]{2}$")
    tz: str
    day_basis: Literal["LST", "LOCAL"] = "LST"
    dsm_location: str | None = None
    dsm_source: Literal["nws_api", "iem"] | None = None
    cli_location: str | None = Field(None, pattern=r"^[A-Z0-9]{3}$")
    pfm_point: str | None = None
    venues: list[VenueEntry] = Field(default_factory=list)

    @field_validator("tz")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown IANA time zone: {v}") from exc
        return v

    @model_validator(mode="after")
    def _dsm_source_needs_location(self) -> StationEntry:
        if self.dsm_source is not None and self.dsm_location is None:
            raise ValueError(f"{self.id}: dsm_source set without dsm_location")
        return self

    @model_validator(mode="after")
    def _unique_venues(self) -> StationEntry:
        keys = [(v.venue, v.kind) for v in self.venues]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{self.id}: duplicate (venue, kind) entry")
        return self


def registry_path() -> Path:
    return Path(os.environ.get("STATIONS_FILE", str(DEFAULT_PATH)))


def load_registry(path: Path | None = None) -> list[StationEntry]:
    p = path or registry_path()
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{p}: expected a list of stations")
    entries = [StationEntry.model_validate(item) for item in raw]
    ids = [e.id for e in entries]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"{p}: duplicate station ids {sorted(dupes)}")
    return entries
