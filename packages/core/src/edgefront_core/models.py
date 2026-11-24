"""ORM models for CONTEXT.md §7 (v1). `hf_observations` is Premium (v2) and deliberately absent.

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
    ForeignKeyConstraint,
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

JsonType = JSON().with_variant(JSONB(), "postgresql")
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


class DsmProduct(Base):
    __tablename__ = "dsm_products"
    __table_args__ = (Index("ix_dsm_station_date", "station_id", "climate_date"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"))
    product_id: Mapped[str] = mapped_column(String(64), unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    climate_date: Mapped[date | None] = mapped_column(Date)
    is_final: Mapped[bool | None] = mapped_column(Boolean)
    max_temp_f: Mapped[int | None] = mapped_column(Integer)
    max_time_local: Mapped[str | None] = mapped_column(String(4))  # HHMM LST as published
    min_temp_f: Mapped[int | None] = mapped_column(Integer)
    min_time_local: Mapped[str | None] = mapped_column(String(4))
    precip_in: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    peak_wind_kt: Mapped[int | None] = mapped_column(Integer)
    peak_wind_dir: Mapped[int | None] = mapped_column(Integer)
    peak_wind_time_local: Mapped[str | None] = mapped_column(String(4))
    raw_text: Mapped[str] = mapped_column(Text)
    decode_errors: Mapped[Any | None] = mapped_column(JsonType)
    source: Mapped[str] = mapped_column(String(64))
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
    update_time: Mapped[datetime | None] = _ts()
    periods: Mapped[Any | None] = mapped_column(JsonType)
    hourly: Mapped[Any | None] = mapped_column(JsonType)
    source: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------- models


class ModelRun(Base):
    __tablename__ = "model_runs"

    model: Mapped[str] = mapped_column(String(16), primary_key=True)
    cycle_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    available_at: Mapped[datetime | None] = _ts()  # when EdgeFront first saw the run
    fetched_at: Mapped[datetime | None] = _ts()
    status: Mapped[str] = mapped_column(String(16), default="seen", server_default="seen")
    source_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class ModelValue(Base):
    """Values at a station for one run. Source lives on the parent model_runs row."""

    __tablename__ = "model_values"
    __table_args__ = (
        ForeignKeyConstraint(
            ["model", "cycle_time"],
            ["model_runs.model", "model_runs.cycle_time"],
            ondelete="CASCADE",
            name="fk_model_values_run",
        ),
        Index("ix_model_values_station", "station_id", "model", "cycle_time"),
    )

    model: Mapped[str] = mapped_column(String(16), primary_key=True)
    cycle_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), primary_key=True)
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    variable: Mapped[str] = mapped_column(String(16), primary_key=True)
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    is_computed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    grid_lat: Mapped[float | None] = mapped_column(Float)
    grid_lon: Mapped[float | None] = mapped_column(Float)


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
