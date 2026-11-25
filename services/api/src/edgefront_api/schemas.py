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
    aliases: list[str] = Field(default_factory=list, description="Extra search terms")
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
    aliases: list[str] = Field(default_factory=list, description="Extra search terms")
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


# ---------------------------------------------------------------- daily summaries (Phase 3)


class WindOut(BaseModel):
    dir_deg: int | None
    speed_mph: int | None
    time_local: str | None = Field(description="HH:MM, local standard time")


class CoversOut(BaseModel):
    date: date
    kind: Literal["so_far", "preliminary", "final"] | None = Field(
        description="DSM: so_far | final. CLI: preliminary (intraday 'valid as of') | final"
    )


class DailySummaryRow(BaseModel):
    product: Literal["CLI", "DSM"]
    product_name: str
    day: Literal["today", "yesterday"]
    status: Literal["ok", "not_issued_yet", "not_available"]
    reason: str | None = Field(None, description="Why there is no product, in plain words")
    covers: CoversOut
    issuer: str | None = Field(None, description="Issuing office / ARTCC, e.g. KFWD, KZFW")
    source: Literal["nws_api", "iem"] | None = None
    source_label: str | None = None
    attribution: str | None = None
    product_id: str | None = None
    issued_at: datetime | None = None
    valid_as_of_local: str | None = Field(
        None, description="HH:MM LST: CLI 'valid as of' or the DSM 'DS HHMM' issue time"
    )
    is_correction: bool = False
    issuances_for_day: int = 0
    max_f: int | None = None
    max_time_local: str | None = None
    min_f: int | None = None
    min_time_local: str | None = None
    precip_in: float | None = None
    precip_trace: bool = False
    normal_high_f: int | None = None
    normal_low_f: int | None = None
    departure_high_f: int | None = None
    departure_low_f: int | None = None
    peak_wind: WindOut | None = None
    peak_gust: WindOut | None = None
    raw_text: str | None = None
    decode_errors: list[str] = Field(default_factory=list)


class DailySummariesResponse(BaseModel):
    generated_at: datetime
    station_id: str
    tz: str
    times_are: Literal["LST"] = "LST"
    status: Literal["ok", "none_available"]
    message: str | None = None
    today: date
    yesterday: date
    rows: list[DailySummaryRow]
    sources: list[SourceRef]


# ---------------------------------------------------------------- NWS forecast (Phase 3)


class ForecastPeriodOut(BaseModel):
    name: str
    start: datetime
    end: datetime
    temperature_f: int | None
    pop_percent: int | None
    short: str | None
    detailed: str | None


class HourSlotOut(BaseModel):
    start: datetime
    temperature_f: int | None
    pop_percent: int | None
    short: str | None


class ForecastResponse(BaseModel):
    generated_at: datetime
    station_id: str
    status: Literal["ok", "no_data", "stale"]
    label: Literal["FORECAST · NWS"] = "FORECAST · NWS"
    source: SourceRef
    office: str | None
    update_time: datetime | None = Field(description="When the office last updated the forecast")
    fetched_at: datetime | None
    today_high_f: int | None = Field(
        description="Today's daytime period (station local date); null once it has ended"
    )
    today_note: str | None = None
    tonight_low_f: int | None
    today: ForecastPeriodOut | None
    tonight: ForecastPeriodOut | None
    hourly: list[HourSlotOut] = Field(description="Next 14 h in 2 h steps (≤ 7 slots)")
    weather_gov_url: str | None
