"""Phase 1: registry and data tables (CONTEXT.md §7; hf_observations is v2 and excluded).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "model_runs",
        sa.Column("model", sa.String(length=16), nullable=False),
        sa.Column("cycle_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="seen", nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("model", "cycle_time"),
    )
    op.create_table(
        "stations",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("official_name", sa.String(length=160), nullable=True),
        sa.Column("city", sa.String(length=80), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("elevation_m", sa.Float(), nullable=True),
        sa.Column("tz", sa.String(length=64), nullable=False),
        sa.Column("day_basis", sa.String(length=8), server_default="LST", nullable=False),
        sa.Column("nws_office", sa.String(length=4), nullable=True),
        sa.Column("grid_x", sa.Integer(), nullable=True),
        sa.Column("grid_y", sa.Integer(), nullable=True),
        sa.Column("dsm_location", sa.String(length=8), nullable=True),
        sa.Column("pfm_point", sa.String(length=120), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrichment_source", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("day_basis IN ('LST', 'LOCAL')", name="ck_stations_day_basis"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "dsm_products",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("station_id", sa.String(length=8), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("climate_date", sa.Date(), nullable=True),
        sa.Column("is_final", sa.Boolean(), nullable=True),
        sa.Column("max_temp_f", sa.Integer(), nullable=True),
        sa.Column("max_time_local", sa.String(length=4), nullable=True),
        sa.Column("min_temp_f", sa.Integer(), nullable=True),
        sa.Column("min_time_local", sa.String(length=4), nullable=True),
        sa.Column("precip_in", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("peak_wind_kt", sa.Integer(), nullable=True),
        sa.Column("peak_wind_dir", sa.Integer(), nullable=True),
        sa.Column("peak_wind_time_local", sa.String(length=4), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column(
            "decode_errors",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["stations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id"),
    )
    op.create_index(
        "ix_dsm_station_date", "dsm_products", ["station_id", "climate_date"], unique=False
    )
    op.create_table(
        "metar_reports",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("station_id", sa.String(length=8), nullable=False),
        sa.Column("report_type", sa.String(length=5), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("raw_hash", sa.String(length=64), nullable=False),
        sa.Column("is_correction", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "corrects_report_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=True,
        ),
        sa.Column("temp_c", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("dewpt_c", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("temp_precision", sa.String(length=6), nullable=True),
        sa.Column("wind_dir_deg", sa.Integer(), nullable=True),
        sa.Column("wind_vrb", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("wind_kt", sa.Integer(), nullable=True),
        sa.Column("gust_kt", sa.Integer(), nullable=True),
        sa.Column("vis_mi", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column(
            "sky",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("altim_inhg", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("slp_hpa", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("max6h_c", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("min6h_c", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("max24h_c", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("min24h_c", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("report_type IN ('METAR', 'SPECI')", name="ck_metar_report_type"),
        sa.CheckConstraint(
            "temp_precision IS NULL OR temp_precision IN ('tenths', 'whole')",
            name="ck_metar_temp_precision",
        ),
        sa.ForeignKeyConstraint(["corrects_report_id"], ["metar_reports.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["stations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "station_id", "observed_at", "report_type", "raw_hash", name="uq_metar_dedupe"
        ),
    )
    op.create_index(
        "ix_metar_station_observed", "metar_reports", ["station_id", "observed_at"], unique=False
    )
    op.create_table(
        "model_values",
        sa.Column("model", sa.String(length=16), nullable=False),
        sa.Column("cycle_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("station_id", sa.String(length=8), nullable=False),
        sa.Column("valid_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("variable", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("is_computed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("grid_lat", sa.Float(), nullable=True),
        sa.Column("grid_lon", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["model", "cycle_time"],
            ["model_runs.model", "model_runs.cycle_time"],
            name="fk_model_values_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["stations.id"],
        ),
        sa.PrimaryKeyConstraint("model", "cycle_time", "station_id", "valid_time", "variable"),
    )
    op.create_index(
        "ix_model_values_station",
        "model_values",
        ["station_id", "model", "cycle_time"],
        unique=False,
    )
    op.create_table(
        "nws_forecasts",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("station_id", sa.String(length=8), nullable=False),
        sa.Column("office", sa.String(length=4), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "periods",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column(
            "hourly",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["stations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_forecast_station_fetched", "nws_forecasts", ["station_id", "fetched_at"], unique=False
    )
    op.create_table(
        "station_venues",
        sa.Column("station_id", sa.String(length=8), nullable=False),
        sa.Column(
            "venue", sa.Enum("kalshi", "polymarket", "robinhood", name="venue"), nullable=False
        ),
        sa.Column("market_kind", sa.Enum("high", "low", name="market_kind"), nullable=False),
        sa.Column("market", sa.String(length=200), nullable=True),
        sa.Column("settlement_source", sa.Text(), nullable=True),
        sa.Column("rules_url", sa.Text(), nullable=True),
        sa.Column("verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("station_id", "venue", "market_kind"),
    )
    op.create_table(
        "daily_high_events",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("station_id", sa.String(length=8), nullable=False),
        sa.Column("climate_date", sa.Date(), nullable=False),
        sa.Column("from_c", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("to_c", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column(
            "report_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["report_id"], ["metar_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["stations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_high_events_observed", "daily_high_events", ["observed_at"], unique=False)
    op.create_index(
        "ix_high_events_station_date",
        "daily_high_events",
        ["station_id", "climate_date"],
        unique=False,
    )


def downgrade() -> None:

    op.drop_index("ix_high_events_station_date", table_name="daily_high_events")
    op.drop_index("ix_high_events_observed", table_name="daily_high_events")
    op.drop_table("daily_high_events")
    op.drop_table("station_venues")
    op.drop_index("ix_forecast_station_fetched", table_name="nws_forecasts")
    op.drop_table("nws_forecasts")
    op.drop_index("ix_model_values_station", table_name="model_values")
    op.drop_table("model_values")
    op.drop_index("ix_metar_station_observed", table_name="metar_reports")
    op.drop_table("metar_reports")
    op.drop_index("ix_dsm_station_date", table_name="dsm_products")
    op.drop_table("dsm_products")
    op.drop_table("stations")
    op.drop_table("model_runs")

    # Postgres keeps enum types after their tables are dropped.
    sa.Enum(name="market_kind").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="venue").drop(op.get_bind(), checkfirst=True)
