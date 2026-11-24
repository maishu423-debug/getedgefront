"""Pydantic response models for /api/v1. Temperatures: °C as stored (1 decimal) + whole °F
for display (half away from zero, §6.1). Times are ISO 8601 UTC."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

DataStatus = Literal["ok", "no_data", "stale"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: Literal["api"] = "api"
    db: Literal["ok", "unreachable"]
    generated_at: datetime


class SourceRef(BaseModel):
    source: str = Field(description="Upstream endpoint the data came from")
    producer: str
    last_success_at: datetime | None = Field(
        None, description="Last successful EdgeFront fetch from this source"
    )


class VenueOut(BaseModel):
    venue: Literal["kalshi", "polymarket", "robinhood"]
    kind: Literal["high", "low"]
    market: str | None
    settlement_source: str | None
    rules_url: str | None
    verified: bool
    verified_at: datetime | None


class ClimateDayOut(BaseModel):
    date: date
    basis: Literal["LST", "LOCAL"]
    start: datetime
    end: datetime
    ends_in_minutes: int
    elapsed_fraction: float


class SkyLayerOut(BaseModel):
    cover: str
    base_ft: int | None
    type: str | None = None


class MetarBrief(BaseModel):
    report_id: int
    report_type: Literal["METAR", "SPECI"]
    observed_at: datetime
    age_minutes: int
    temp_c: float | None
    temp_f: int | None
    temp_precision: Literal["tenths", "whole"] | None


class MetarOut(MetarBrief):
    raw_text: str
    is_correction: bool
    superseded: bool = Field(description="A later COR replaced this report")
    fetched_at: datetime
    dewpt_c: float | None
    dewpt_f: int | None
    rh_computed: float | None = Field(description="Computed from T/Td (Magnus); not observed")
    wind_dir_deg: int | None
    wind_compass: str | None
    wind_vrb: bool
    wind_kt: int | None
    gust_kt: int | None
    vis_mi: float | None
    sky: list[SkyLayerOut]
    altim_inhg: float | None
    slp_hpa: float | None
    max6h_c: float | None
    min6h_c: float | None
    max24h_c: float | None
    min24h_c: float | None


class HighSoFarOut(BaseModel):
    value_c: float
    value_f: int
    precision: Literal["tenths", "whole"] | None
    kind: Literal["report", "max6h"] = Field(
        description="'report': a METAR/SPECI temperature; 'max6h': a 6-hour max group whose "
        "window lies entirely inside the climate day"
    )
    report_id: int
    report_type: Literal["METAR", "SPECI"]
    observed_at: datetime = Field(description="Observation time of the report it came from")


class StationMeta(BaseModel):
    id: str
    name: str
    official_name: str | None
    city: str
    state: str
    lat: float | None
    lon: float | None
    elevation_m: float | None
    tz: str
    std_utc_offset_minutes: int
    zone_group: str
    local_time: datetime
    nws_office: str | None
    grid_x: int | None
    grid_y: int | None
    dsm_location: str | None
    pfm_point: str | None
    venues: list[VenueOut]
    venues_verified: bool = Field(description="False while any venue mapping is unverified")


class BoardRow(BaseModel):
    id: str
    name: str
    city: str
    state: str
    tz: str
    zone_group: str
    std_utc_offset_minutes: int
    local_time: datetime
    venues: list[VenueOut]
    latest: MetarBrief | None
    high_so_far: HighSoFarOut | None
    nws_today_high_f: int | None = Field(None, description="Filled from Phase 3 (NWS forecast)")
    is_stale: bool
    fresh_high: bool = Field(description="A new high was observed within the last 60 minutes")
    climate_day: ClimateDayOut


class StationsResponse(BaseModel):
    generated_at: datetime
    status: DataStatus
    source: SourceRef
    stale_after_minutes: int
    stations: list[BoardRow]


class StationResponse(BaseModel):
    generated_at: datetime
    station: StationMeta
    climate_day: ClimateDayOut


class CurrentResponse(BaseModel):
    generated_at: datetime
    station_id: str
    status: DataStatus
    source: SourceRef
    stale_after_minutes: int
    is_stale: bool
    latest: MetarOut | None
    high_so_far: HighSoFarOut | None
    climate_day: ClimateDayOut


class MetarsResponse(BaseModel):
    generated_at: datetime
    station_id: str
    status: DataStatus
    hours: int
    source: SourceRef
    reports: list[MetarOut] = Field(description="Newest first, raw text exactly as received")


class ObservedPoint(BaseModel):
    report_id: int
    report_type: Literal["METAR", "SPECI"]
    observed_at: datetime
    temp_c: float | None
    temp_f: int | None
    dewpt_c: float | None
    dewpt_f: int | None
    rh_computed: float | None
    wind_dir_deg: int | None
    wind_vrb: bool
    wind_kt: int | None
    gust_kt: int | None
    altim_inhg: float | None
    sky_cover: str | None = Field(description="Greatest cover reported (CLR…OVC/VV)")
    sky: list[SkyLayerOut]


class Gap(BaseModel):
    start: datetime
    end: datetime
    minutes: int


class ObservedResponse(BaseModel):
    generated_at: datetime
    station_id: str
    status: DataStatus
    hours: int
    source: SourceRef
    gap_minutes: int = Field(description="Gaps longer than this are listed and must not be bridged")
    points: list[ObservedPoint] = Field(description="Oldest first; corrected reports only once")
    gaps: list[Gap]


class HighEventOut(BaseModel):
    station_id: str
    station_name: str
    city: str
    climate_date: date
    from_c: float
    from_f: int
    to_c: float
    to_f: int
    observed_at: datetime
    report_id: int
    report_type: Literal["METAR", "SPECI"]


class FeedResponse(BaseModel):
    generated_at: datetime
    source: SourceRef
    events: list[HighEventOut]


class SourceStatus(BaseModel):
    key: str
    label: str
    producer: str
    schedule_seconds: int
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    last_error_at: datetime | None
    last_item_time: datetime | None
    healthy: bool = Field(description="Last success within 3x the schedule")


class StatusResponse(BaseModel):
    generated_at: datetime
    sources: list[SourceStatus]
