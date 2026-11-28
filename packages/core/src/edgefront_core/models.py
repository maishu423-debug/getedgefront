"""ORM models for CONTEXT.md §7 (v1) plus the v2 tables (`hf_observations`, `hf_files`: Phase 9).

Portable types: JSON becomes JSONB on Postgres; BigInteger ids become INTEGER on SQLite so
autoincrement works in the local/test database.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# none_as_null: Python None is stored as SQL NULL, not the JSON literal "null" (so
# `decode_errors IS NULL` means "no errors").
JsonType = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
BigId = BigInteger().with_variant(Integer(), "sqlite")
TempC = Numeric(4, 1, asdecimal=True)


class Base(DeclarativeBase):
    pass


class Venue(enum.StrEnum):
    kalshi = "kalshi"
    polymarket = "polymarket"
    robinhood = "robinhood"


class MarketKind(enum.StrEnum):
    high = "high"
    low = "low"


def _ts(nullable: bool = True) -> Mapped[Any]:
    return mapped_column(DateTime(timezone=True), nullable=nullable)


# ---------------------------------------------------------------- registry


class Station(Base):
    __tablename__ = "stations"
    __table_args__ = (
        CheckConstraint("day_basis IN ('LST', 'LOCAL')", name="ck_stations_day_basis"),
    )

    id: Mapped[str] = mapped_column(String(8), primary_key=True)  # ICAO, e.g. KNYC
    name: Mapped[str] = mapped_column(String(120))  # EdgeFront display name (from stations.yaml)
    official_name: Mapped[str | None] = mapped_column(String(160))  # upstream name (enrichment)
    city: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(2))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    elevation_m: Mapped[float | None] = mapped_column(Float)
    tz: Mapped[str] = mapped_column(String(64))  # IANA
    day_basis: Mapped[str] = mapped_column(String(8), default="LST", server_default="LST")
    nws_office: Mapped[str | None] = mapped_column(String(4))  # /points gridId
    grid_x: Mapped[int | None] = mapped_column(Integer)
    grid_y: Mapped[int | None] = mapped_column(Integer)
    dsm_location: Mapped[str | None] = mapped_column(String(8))
    pfm_point: Mapped[str | None] = mapped_column(String(120))  # PFM point name line
    cli_location: Mapped[str | None] = mapped_column(String(8))  # CLI<LOC> product location
    dsm_source: Mapped[str | None] = mapped_column(String(8))  # nws_api | iem | None
    aliases: Mapped[Any | None] = mapped_column(JsonType)  # list[str] search terms
    # "F" (ASOS, whole °F; METAR tenths °C are conversions) or "C" (KBKF). v2 Phase 9, Q36.
    native_temp_unit: Mapped[str] = mapped_column(String(1), default="F", server_default="F")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    enriched_at: Mapped[datetime | None] = _ts()
    enrichment_source: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StationVenue(Base):
    __tablename__ = "station_venues"

    station_id: Mapped[str] = mapped_column(
        ForeignKey("stations.id", ondelete="CASCADE"), primary_key=True
    )
    venue: Mapped[Venue] = mapped_column(
        Enum(Venue, name="venue", native_enum=True, validate_strings=True), primary_key=True
    )
    market_kind: Mapped[MarketKind] = mapped_column(
        Enum(MarketKind, name="market_kind", native_enum=True, validate_strings=True),
        primary_key=True,
    )
    market: Mapped[str | None] = mapped_column(String(200))
    settlement_source: Mapped[str | None] = mapped_column(Text)
    rules_url: Mapped[str | None] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    verified_at: Mapped[datetime | None] = _ts()


# ---------------------------------------------------------------- observations


class MetarReport(Base):
    __tablename__ = "metar_reports"
    __table_args__ = (
        UniqueConstraint(
            "station_id", "observed_at", "report_type", "raw_hash", name="uq_metar_dedupe"
        ),
        Index("ix_metar_station_observed", "station_id", "observed_at"),
        CheckConstraint("report_type IN ('METAR', 'SPECI')", name="ck_metar_report_type"),
        CheckConstraint(
            "temp_precision IS NULL OR temp_precision IN ('tenths', 'whole')",
            name="ck_metar_temp_precision",
        ),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"))
    report_type: Mapped[str] = mapped_column(String(5))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_text: Mapped[str] = mapped_column(Text)
    raw_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex of raw_text
    is_correction: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    corrects_report_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("metar_reports.id", ondelete="SET NULL")
    )
    temp_c: Mapped[Decimal | None] = mapped_column(TempC)
    dewpt_c: Mapped[Decimal | None] = mapped_column(TempC)
    temp_precision: Mapped[str | None] = mapped_column(String(6))
    wind_dir_deg: Mapped[int | None] = mapped_column(Integer)
    wind_vrb: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    wind_kt: Mapped[int | None] = mapped_column(Integer)
    gust_kt: Mapped[int | None] = mapped_column(Integer)
    vis_mi: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    sky: Mapped[Any | None] = mapped_column(JsonType)
    altim_inhg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    slp_hpa: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    max6h_c: Mapped[Decimal | None] = mapped_column(TempC)
    min6h_c: Mapped[Decimal | None] = mapped_column(TempC)
    max24h_c: Mapped[Decimal | None] = mapped_column(TempC)
    min24h_c: Mapped[Decimal | None] = mapped_column(TempC)
    source: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DailyHighEvent(Base):
    __tablename__ = "daily_high_events"
    __table_args__ = (
        Index("ix_high_events_observed", "observed_at"),
        Index("ix_high_events_station_date", "station_id", "climate_date"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"))
    climate_date: Mapped[date] = mapped_column(Date)
    from_c: Mapped[Decimal] = mapped_column(TempC)
    to_c: Mapped[Decimal] = mapped_column(TempC)
    report_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("metar_reports.id", ondelete="CASCADE")
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CliProduct(Base):
    """NWS Daily Climate Report (CLI). Every issuance is kept; for a (station, climate_date) the
    latest final (corrections included) supersedes earlier ones."""

    __tablename__ = "cli_products"
    __table_args__ = (
        Index("ix_cli_station_date", "station_id", "climate_date"),
        CheckConstraint(
            "report_kind IS NULL OR report_kind IN ('final', 'preliminary')", name="ck_cli_kind"
        ),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"))
    product_id: Mapped[str] = mapped_column(String(64), unique=True)  # api.weather.gov id
    issuer: Mapped[str | None] = mapped_column(String(8))
    wmo_header: Mapped[str | None] = mapped_column(String(40))
    is_correction: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    climate_date: Mapped[date | None] = mapped_column(Date)
    report_kind: Mapped[str | None] = mapped_column(String(12))
    valid_as_of_local: Mapped[str | None] = mapped_column(String(5))  # "HH:MM" LST
    max_temp_f: Mapped[int | None] = mapped_column(Integer)
    max_time_local: Mapped[str | None] = mapped_column(String(5))
    min_temp_f: Mapped[int | None] = mapped_column(Integer)
    min_time_local: Mapped[str | None] = mapped_column(String(5))
    precip_in: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    precip_trace: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    normal_high_f: Mapped[int | None] = mapped_column(Integer)
    normal_low_f: Mapped[int | None] = mapped_column(Integer)
    departure_high_f: Mapped[int | None] = mapped_column(Integer)
    departure_low_f: Mapped[int | None] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    raw_hash: Mapped[str] = mapped_column(String(64))
    decode_errors: Mapped[Any | None] = mapped_column(JsonType)
    source: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DsmProduct(Base):
    """ASOS Daily Summary. `issue_key` is the DS HHMM issue time ('0700') or 'FINAL' for the
    next-day final without one; dedupe on (station, climate_date, issue_key, raw_hash)."""

    __tablename__ = "dsm_products"
    __table_args__ = (
        Index("ix_dsm_station_date", "station_id", "climate_date"),
        UniqueConstraint(
            "station_id", "climate_date", "issue_key", "raw_hash", name="uq_dsm_dedupe"
        ),
        CheckConstraint("source IN ('nws_api', 'iem')", name="ck_dsm_source"),
        CheckConstraint(
            "report_kind IS NULL OR report_kind IN ('so_far', 'final')", name="ck_dsm_kind"
        ),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"))
    product_id: Mapped[str] = mapped_column(String(80), unique=True)  # source-specific id
    source: Mapped[str] = mapped_column(String(16))  # nws_api | iem
    issuer: Mapped[str | None] = mapped_column(String(8))
    wmo_header: Mapped[str | None] = mapped_column(String(40))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    climate_date: Mapped[date | None] = mapped_column(Date)
    report_kind: Mapped[str | None] = mapped_column(String(8))
    issue_key: Mapped[str] = mapped_column(String(5))  # "HHMM" LST or "FINAL"
    is_correction: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    max_temp_f: Mapped[int | None] = mapped_column(Integer)
    max_time_local: Mapped[str | None] = mapped_column(String(5))  # "HH:MM" LST
    min_temp_f: Mapped[int | None] = mapped_column(Integer)
    min_time_local: Mapped[str | None] = mapped_column(String(5))
    precip_in: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    precip_trace: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    peak_wind_dir: Mapped[int | None] = mapped_column(Integer)
    peak_wind_speed: Mapped[int | None] = mapped_column(Integer)
    peak_wind_time_local: Mapped[str | None] = mapped_column(String(5))
    peak_gust_dir: Mapped[int | None] = mapped_column(Integer)
    peak_gust_speed: Mapped[int | None] = mapped_column(Integer)
    peak_gust_time_local: Mapped[str | None] = mapped_column(String(5))
    wind_speed_unit: Mapped[str | None] = mapped_column(String(8))
    raw_text: Mapped[str] = mapped_column(Text)
    raw_hash: Mapped[str] = mapped_column(String(64))
    decode_errors: Mapped[Any | None] = mapped_column(JsonType)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NwsForecast(Base):
    __tablename__ = "nws_forecasts"
    __table_args__ = (Index("ix_forecast_station_fetched", "station_id", "fetched_at"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"))
    office: Mapped[str] = mapped_column(String(4))
    generated_at: Mapped[datetime | None] = _ts()
    update_time: Mapped[datetime | None] = _ts()  # forecast updateTime (office edit time)
    hourly_update_time: Mapped[datetime | None] = _ts()
    periods: Mapped[Any | None] = mapped_column(JsonType)
    hourly: Mapped[Any | None] = mapped_column(JsonType)
    forecast_expires_at: Mapped[datetime | None] = _ts()
    hourly_expires_at: Mapped[datetime | None] = _ts()
    forecast_last_modified: Mapped[str | None] = mapped_column(String(40))
    hourly_last_modified: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------- models


class ModelRun(Base):
    """One run of one model as EdgeFront received it (CONTEXT §4.4, §7).

    `issuer` separates runs that share a model and cycle time but come from different
    producers: the PFM is issued per NWS office (office id), everything else uses ''.
    """

    __tablename__ = "model_runs"
    __table_args__ = (
        UniqueConstraint("model", "cycle_time", "issuer", name="uq_model_runs_key"),
        CheckConstraint("status IN ('partial', 'complete', 'failed')", name="ck_model_runs_status"),
        Index("ix_model_runs_model_cycle", "model", "cycle_time"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    model: Mapped[str] = mapped_column(String(16))
    cycle_time: Mapped[datetime] = _ts(nullable=False)
    issuer: Mapped[str] = mapped_column(String(8), default="", server_default="")
    available_at: Mapped[datetime] = _ts(nullable=False)  # when EdgeFront first saw the run
    fetched_at: Mapped[datetime | None] = _ts()  # last successful download for this run
    updated_at: Mapped[datetime | None] = _ts()
    status: Mapped[str] = mapped_column(String(16), default="partial", server_default="partial")
    source_url: Mapped[str | None] = mapped_column(Text)
    steps_expected: Mapped[int | None] = mapped_column(Integer)
    steps_fetched: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text)


class ModelRunStation(Base):
    """Per run and station: where the value comes from, or why there is none."""

    __tablename__ = "model_run_stations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ok', 'not_available', 'failed')", name="ck_model_run_stations_status"
        ),
    )

    run_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("model_runs.id", ondelete="CASCADE"), primary_key=True
    )
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(Text)
    point_name: Mapped[str | None] = mapped_column(String(160))  # PFM point / bulletin id
    grid_lat: Mapped[float | None] = mapped_column(Float)
    grid_lon: Mapped[float | None] = mapped_column(Float)
    grid_distance_km: Mapped[float | None] = mapped_column(Float)
    height_m: Mapped[float | None] = mapped_column(Float)  # model orography / point elevation
    land_fraction: Mapped[float | None] = mapped_column(Float)


class ModelValue(Base):
    """One value at a station for one run. Source lives on the parent model_runs row.

    `value`/`unit` are canonical (degC, kt, pct, category); `native_value`/`native_unit` are what
    the product printed (e.g. degF, mph). Categorical cloud has value NULL (or the plotting
    midpoint is applied in the API, never stored) and `category` set.
    """

    __tablename__ = "model_values"
    __table_args__ = (Index("ix_model_values_station", "station_id", "run_id"),)

    run_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("model_runs.id", ondelete="CASCADE"), primary_key=True
    )
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), primary_key=True)
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    variable: Mapped[str] = mapped_column(String(16), primary_key=True)
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    native_value: Mapped[float | None] = mapped_column(Float)
    native_unit: Mapped[str | None] = mapped_column(String(16))
    category: Mapped[str | None] = mapped_column(String(4))
    is_computed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


# ---------------------------------------------------------------- ops


class SourceHealth(Base):
    """Last success/attempt/error per ingest source; drives the data status strip."""

    __tablename__ = "source_health"

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_success_at: Mapped[datetime | None] = _ts()
    last_attempt_at: Mapped[datetime | None] = _ts()
    last_error_at: Mapped[datetime | None] = _ts()
    last_error: Mapped[str | None] = mapped_column(Text)
    last_item_time: Mapped[datetime | None] = _ts()
    notes: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------- v2 Phase 9: 5-minute data


class HfObservation(Base):
    """One 5-minute observation from MADIS "1-minute ASOS" (HFMETAR), registry stations only.

    Values are converted back to the units the station reports in and snapped to their verified
    grid (docs/formats/hfmetar.md): temperature/dew point whole °C, wind whole kt, altimeter
    0.01 inHg. A value more than 0.01 off its grid is kept as is and flagged in `qc`
    ("off_grid"), never guessed. Missing stays null. Retention: 7 days.
    """

    __tablename__ = "hf_observations"

    station_id: Mapped[str] = mapped_column(
        ForeignKey("stations.id", ondelete="CASCADE"), primary_key=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    temp_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    temp_precision: Mapped[str | None] = mapped_column(String(8))  # whole_c | tenths_c | off_grid
    dewpt_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    wind_dir_deg: Mapped[int | None] = mapped_column(Integer)
    wind_kt: Mapped[int | None] = mapped_column(Integer)
    gust_kt: Mapped[int | None] = mapped_column(Integer)
    altim_inhg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    vis_mi: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))  # 1/16 mi steps
    precip_in: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # Per variable, as provided: {"temperature": {"dd": "V", "qca": 1023, "qcr": 0}, ...}
    qc: Mapped[Any | None] = mapped_column(JsonType)
    # v2 Phase 10b: the record exactly as transmitted (a comma-separated MADIS LDAD record, not a
    # METAR), sky layers [{"cover": "BKN", "base_ft": 1500}] and present weather ("-RA"). Like QC,
    # these are kept current on rewrites without counting as a value revision.
    raw_message: Mapped[str | None] = mapped_column(Text)
    sky: Mapped[Any | None] = mapped_column(JsonType)
    pres_wx: Mapped[str | None] = mapped_column(String(40))
    source_file: Mapped[str] = mapped_column(String(40))  # first file the reading appeared in
    received_at: Mapped[datetime | None] = _ts()  # MADIS receivedTime
    file_modified_at: Mapped[datetime | None] = _ts()  # modified_at of that first file version
    fetched_at: Mapped[datetime] = _ts(nullable=False)  # when we first downloaded it
    ingested_at: Mapped[datetime] = _ts(nullable=False)  # first stored
    updated_at: Mapped[datetime] = _ts(nullable=False)  # last value or QC change
    row_hash: Mapped[str] = mapped_column(String(64))  # sha256 of the values (not QC)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # First stored by a catch-up (the worker's first run, or a file deferred by the per-run cap):
    # its stamps say nothing about live delay, so latency stats leave it out.
    backfill: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())


class HfFile(Base):
    """The HFMETAR files we have processed: a file is downloaded again only when its
    (modified_at, size) changes."""

    __tablename__ = "hf_files"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)  # hfmetar.YYYYMMDD_HH00.gz
    modified_at: Mapped[datetime] = _ts(nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    processed_at: Mapped[datetime] = _ts(nullable=False)
    records: Mapped[int] = mapped_column(Integer)  # all stations in the file
    our_rows: Mapped[int] = mapped_column(Integer)  # registry stations
