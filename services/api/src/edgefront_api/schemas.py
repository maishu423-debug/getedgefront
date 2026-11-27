"""Pydantic response models for /api/v1. Temperatures: °C as stored (1 decimal) + whole °F
for display (NWS rounding: .5 rounds up, FMH-1 2.6.3; §6.1). Times are ISO 8601 UTC."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

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


class TempValueOut(BaseModel):
    """A temperature with both the exact and the whole-°F value (v2 Phase 9 B9)."""

    c: float = Field(description="Degrees Celsius as reported")
    f_exact: float = Field(description="°C * 9/5 + 32, not rounded")
    f_rounded: int = Field(description="Whole °F, NWS rounding (.5 rounds up, FMH-1 2.6.3)")
    f_possible: list[int] | None = Field(
        description="Whole-°F readings an ASOS station (measures in °F) could have made to give "
        "this °C: one for tenths, one or two for whole °C. None at stations measuring in °C"
    )
    precision: Literal["tenths_c", "whole_c"] = Field(
        description="'whole_c': only good to ±0.5 °C (±0.9 °F); show the uncertainty"
    )
    source: Literal["metar_tgroup", "metar_body", "metar_6h_group", "hfmetar"]
    observed_at: datetime


class MetarBrief(BaseModel):
    report_id: int
    report_type: Literal["METAR", "SPECI"]
    observed_at: datetime
    age_minutes: int
    temp_c: float | None
    temp_f: int | None
    temp_precision: Literal["tenths", "whole"] | None
    temp: TempValueOut | None = Field(None, description="Current temperature, exact and rounded")


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
    temp: TempValueOut | None = Field(None, description="The same value, exact and rounded")


class LowSoFarOut(BaseModel):
    """Lowest temperature of the climate day so far, from METAR (v2 Phase 9 B6)."""

    value_c: float
    value_f: int
    precision: Literal["tenths", "whole"] | None
    kind: Literal["report", "min6h"] = Field(
        description="'report': a METAR/SPECI temperature; 'min6h': a 6-hour minimum group "
        "whose window lies entirely inside the climate day"
    )
    report_id: int
    report_type: Literal["METAR", "SPECI"]
    observed_at: datetime = Field(description="Observation time of the report it came from")
    temp: TempValueOut


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
    low_so_far: LowSoFarOut | None = None
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
    low_so_far: LowSoFarOut | None = None
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


class HfStageOut(BaseModel):
    count: int
    p50_s: float | None
    p95_s: float | None


class HfLatencyOut(BaseModel):
    window_hours: int
    rows: int
    excluded_late: int = Field(
        description="Readings first fetched over 60 min after observation (backfill or catching "
        "up after an outage): left out of the percentiles"
    )
    received: HfStageOut = Field(description="Observation -> MADIS received")
    file_modified: HfStageOut = Field(description="Observation -> LDM file written")
    fetched: HfStageOut = Field(description="Observation -> EdgeFront download")
    ingested: HfStageOut = Field(description="Observation -> stored")
    per_station: dict[str, dict[str, HfStageOut]]


class HfFileOut(BaseModel):
    name: str
    modified_at: datetime
    processed_at: datetime
    our_rows: int


class HfRoundingCheckOut(BaseModel):
    pairs: int = Field(description="5-minute readings paired with a METAR/SPECI at the same minute")
    matches: int
    mismatches: int
    mismatch_examples: list[str] = Field(description="'KDFW 2026-11-27T15:10:00Z', up to 5")


class HfStatusOut(BaseModel):
    """5-minute HFMETAR pipeline (v2 Phase 9 B8). Kept out of `sources` so the public status
    strip and the web health check are unchanged."""

    last_success_at: datetime | None
    last_error_at: datetime | None
    last_file: HfFileOut | None
    last_reading_at: datetime | None
    stations_reporting_30m: list[str]
    stations_missing_30m: list[str] = Field(description="Active stations without a reading")
    latency: HfLatencyOut
    rounding_check: HfRoundingCheckOut


class StatusResponse(BaseModel):
    generated_at: datetime
    sources: list[SourceStatus]
    hfmetar: HfStatusOut | None = None


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


# ---------------------------------------------------------------- model guidance (Phase 5)

ModelVariable = Literal["temp", "dewpt", "wind", "cloud", "rh"]


class ModelWindow(BaseModel):
    span: Literal["today", "48h"]
    start: datetime = Field(description="UTC; the climate day's start (LST)")
    end: datetime = Field(description="UTC; climate-day end (today) or start + 48 h")
    start_local: datetime = Field(description="Same instant in local standard time")
    end_local: datetime
    climate_date: date
    basis: Literal["LST", "LOCAL"]


class ModelPoint(BaseModel):
    valid_time: datetime
    value: float | None = Field(
        description="Display unit: whole °F, whole kt, whole %; categorical cloud → the plotting "
        "midpoint (§6.5 for MOS/LAMP; the PFM's own range midpoints for PFM). The category is "
        "the data."
    )
    category: str | None = Field(None, description="Cloud code as printed (CL FW SC BK OV B1 B2)")
    category_range: str | None = Field(
        None, description="Sky-cover range of the code where the product defines one (PFM)"
    )
    is_computed: bool = Field(False, description="RH computed from T/Td (Magnus)")


class ModelRunOut(BaseModel):
    cycle_time: datetime
    issuer: str | None = Field(None, description="NWS office for PFM")
    available_at: datetime = Field(description="When EdgeFront first received the run")
    fetched_at: datetime | None
    status: Literal["partial", "complete", "failed"]
    steps_expected: int | None
    steps_fetched: int
    source_url: str | None
    stale: bool = Field(description="Received more than 2x the model's cycle interval ago")


class ModelGrid(BaseModel):
    lat: float | None
    lon: float | None
    distance_km: float | None
    height_m: float | None = Field(None, description="Model orography / PFM point elevation")
    point_name: str | None = None


class ModelSeries(BaseModel):
    id: str
    label: str
    group: Literal["global", "ai", "statistical", "nws"]
    producer: str
    colour_token: str
    licence: str | None
    available: bool
    reason: str | None = Field(None, description="Why there is no line, in plain words")
    reason_code: Literal["no_run", "no_station", "no_variable", "station_failed"] | None = None
    kind: Literal["continuous", "categorical"] | None
    native_unit: str | None
    native_step_hours: list[int]
    run: ModelRunOut | None
    grid: ModelGrid | None
    points: list[ModelPoint] = Field(description="Native valid times only, oldest first")


class ObservedOverlay(BaseModel):
    source: SourceRef
    points: list[ModelPoint] = Field(description="Effective METAR/SPECI values in the window")


class ModelsResponse(BaseModel):
    generated_at: datetime
    station_id: str
    station_name: str
    variable: ModelVariable
    unit: Literal["degF", "kt", "pct"]
    now: datetime
    window: ModelWindow
    observed: ObservedOverlay
    models: list[ModelSeries]


# ---------------------------------------------------------------- Premium: 5-minute data (Phase 9)

HF_LABEL = "5-minute ASOS data (NOAA MADIS)"
HF_ATTRIBUTION = (
    "5-minute ASOS observations from the NOAA Meteorological Assimilation Data Ingest System "
    "(MADIS), provided by the FAA. Data as received; not official METAR observations."
)


class HfSourceRef(BaseModel):
    source: str = HF_LABEL
    producer: str = "FAA ASOS via NOAA MADIS"
    attribution: str = HF_ATTRIBUTION
    last_success_at: datetime | None = None


class HfReadingOut(BaseModel):
    observed_at: datetime
    age_minutes: int
    temp: TempValueOut | None = Field(
        description="Whole °C from MADIS with exact/rounded °F and the possible station readings; "
        "None when missing or off its grid"
    )
    temp_c: float | None
    temp_precision: Literal["whole_c", "tenths_c", "off_grid"] | None
    dewpt_c: float | None
    wind_dir_deg: int | None
    wind_kt: int | None
    gust_kt: int | None
    altim_inhg: float | None
    vis_mi: float | None
    precip_in: float | None
    qc_temp: str | None = Field(description="MADIS data descriptor for temperature (V, Q, X, …)")
    qc_failed: bool = Field(description="Temperature descriptor X, Q or B: left out of high/low")
    qc: dict[str, Any] | None = Field(description="MADIS QC flags per variable, as provided")
    revision: int = Field(description="How often a measured value of this reading changed")
    received_at: datetime | None
    ingested_at: datetime


class HfExtremeOut(BaseModel):
    value_c: float
    precision: Literal["whole_c", "tenths_c"]
    observed_at: datetime
    temp: TempValueOut


class HfSoFarOut(BaseModel):
    """5-minute high and low of the climate day so far (v2 Phase 9 B6)."""

    high: HfExtremeOut | None
    low: HfExtremeOut | None
    readings: int = Field(description="5-minute readings inside the climate day so far")
    used: int
    excluded_qc_count: int = Field(description="QC-failed readings (X/Q/B) left out")
    excluded_off_grid_count: int
    missing_temp_count: int


class MetarSideOut(BaseModel):
    latest: MetarBrief | None
    high_so_far: HighSoFarOut | None
    low_so_far: LowSoFarOut | None


class HfSeriesResponse(BaseModel):
    generated_at: datetime
    station_id: str
    hours: int
    in_feed: bool = Field(description="False: this station is not in the 5-minute feed")
    source: HfSourceRef
    readings: list[HfReadingOut] = Field(description="Oldest first")


class HfCurrentResponse(BaseModel):
    generated_at: datetime
    station_id: str
    status: DataStatus
    stale_after_minutes: int
    in_feed: bool
    source: HfSourceRef
    latest: HfReadingOut | None
    so_far: HfSoFarOut
    metar: MetarSideOut = Field(description="The hourly METAR values, side by side")
    climate_day: ClimateDayOut


class MapStationOut(BaseModel):
    station_id: str
    name: str
    city: str
    state: str
    lat: float | None
    lon: float | None
    status: DataStatus
    in_feed: bool
    hf_latest: HfReadingOut | None
    hf_so_far: HfSoFarOut
    metar: MetarSideOut


class MapResponse(BaseModel):
    generated_at: datetime
    source: HfSourceRef
    stations: list[MapStationOut]
