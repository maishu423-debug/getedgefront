"""Phase 3: CLI products, DSM products (rebuilt: source/issuer/issue_key/dedupe), forecast caching
columns, stations.cli_location.

`dsm_products` had never held data (Phase 3 is its first writer), so it is dropped and recreated
rather than altered column by column (portable to SQLite).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
BIGID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _ts(name: str, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.add_column("stations", sa.Column("cli_location", sa.String(8), nullable=True))
    op.add_column("stations", sa.Column("dsm_source", sa.String(8), nullable=True))

    op.create_table(
        "cli_products",
        sa.Column("id", BIGID, autoincrement=True, nullable=False),
        sa.Column("station_id", sa.String(8), sa.ForeignKey("stations.id"), nullable=False),
        sa.Column("product_id", sa.String(64), nullable=False),
        sa.Column("issuer", sa.String(8)),
        sa.Column("wmo_header", sa.String(40)),
        sa.Column("is_correction", sa.Boolean(), server_default=sa.false(), nullable=False),
        _ts("issued_at", nullable=False),
        sa.Column("climate_date", sa.Date()),
        sa.Column("report_kind", sa.String(12)),
        sa.Column("valid_as_of_local", sa.String(5)),
        sa.Column("max_temp_f", sa.Integer()),
        sa.Column("max_time_local", sa.String(5)),
        sa.Column("min_temp_f", sa.Integer()),
        sa.Column("min_time_local", sa.String(5)),
        sa.Column("precip_in", sa.Numeric(5, 2)),
        sa.Column("precip_trace", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("normal_high_f", sa.Integer()),
        sa.Column("normal_low_f", sa.Integer()),
        sa.Column("departure_high_f", sa.Integer()),
        sa.Column("departure_low_f", sa.Integer()),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("raw_hash", sa.String(64), nullable=False),
        sa.Column("decode_errors", JSON),
        sa.Column("source", sa.String(64), nullable=False),
        _ts("fetched_at", nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "report_kind IS NULL OR report_kind IN ('final', 'preliminary')", name="ck_cli_kind"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id"),
    )
    op.create_index("ix_cli_station_date", "cli_products", ["station_id", "climate_date"])

    op.drop_index("ix_dsm_station_date", table_name="dsm_products")
    op.drop_table("dsm_products")
    op.create_table(
        "dsm_products",
        sa.Column("id", BIGID, autoincrement=True, nullable=False),
        sa.Column("station_id", sa.String(8), sa.ForeignKey("stations.id"), nullable=False),
        sa.Column("product_id", sa.String(80), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("issuer", sa.String(8)),
        sa.Column("wmo_header", sa.String(40)),
        _ts("issued_at", nullable=False),
        sa.Column("climate_date", sa.Date()),
        sa.Column("report_kind", sa.String(8)),
        sa.Column("issue_key", sa.String(5), nullable=False),
        sa.Column("is_correction", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("max_temp_f", sa.Integer()),
        sa.Column("max_time_local", sa.String(5)),
        sa.Column("min_temp_f", sa.Integer()),
        sa.Column("min_time_local", sa.String(5)),
        sa.Column("precip_in", sa.Numeric(5, 2)),
        sa.Column("precip_trace", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("peak_wind_dir", sa.Integer()),
        sa.Column("peak_wind_speed", sa.Integer()),
        sa.Column("peak_wind_time_local", sa.String(5)),
        sa.Column("peak_gust_dir", sa.Integer()),
        sa.Column("peak_gust_speed", sa.Integer()),
        sa.Column("peak_gust_time_local", sa.String(5)),
        sa.Column("wind_speed_unit", sa.String(8)),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("raw_hash", sa.String(64), nullable=False),
        sa.Column("decode_errors", JSON),
        _ts("fetched_at", nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("source IN ('nws_api', 'iem')", name="ck_dsm_source"),
        sa.CheckConstraint(
            "report_kind IS NULL OR report_kind IN ('so_far', 'final')", name="ck_dsm_kind"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id"),
        sa.UniqueConstraint(
            "station_id", "climate_date", "issue_key", "raw_hash", name="uq_dsm_dedupe"
        ),
    )
    op.create_index("ix_dsm_station_date", "dsm_products", ["station_id", "climate_date"])

    op.add_column("nws_forecasts", _ts("hourly_update_time"))
    op.add_column("nws_forecasts", _ts("forecast_expires_at"))
    op.add_column("nws_forecasts", _ts("hourly_expires_at"))
    op.add_column("nws_forecasts", sa.Column("forecast_last_modified", sa.String(40)))
    op.add_column("nws_forecasts", sa.Column("hourly_last_modified", sa.String(40)))


def downgrade() -> None:
    with op.batch_alter_table("nws_forecasts") as b:
        for c in (
            "hourly_last_modified",
            "forecast_last_modified",
            "hourly_expires_at",
            "forecast_expires_at",
            "hourly_update_time",
        ):
            b.drop_column(c)

    op.drop_index("ix_dsm_station_date", table_name="dsm_products")
    op.drop_table("dsm_products")
    op.create_table(  # Phase 1 shape
        "dsm_products",
        sa.Column("id", BIGID, autoincrement=True, nullable=False),
        sa.Column("station_id", sa.String(8), sa.ForeignKey("stations.id"), nullable=False),
        sa.Column("product_id", sa.String(64), nullable=False),
        _ts("issued_at", nullable=False),
        sa.Column("climate_date", sa.Date()),
        sa.Column("is_final", sa.Boolean()),
        sa.Column("max_temp_f", sa.Integer()),
        sa.Column("max_time_local", sa.String(4)),
        sa.Column("min_temp_f", sa.Integer()),
        sa.Column("min_time_local", sa.String(4)),
        sa.Column("precip_in", sa.Numeric(5, 2)),
        sa.Column("peak_wind_kt", sa.Integer()),
        sa.Column("peak_wind_dir", sa.Integer()),
        sa.Column("peak_wind_time_local", sa.String(4)),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("decode_errors", JSON),
        sa.Column("source", sa.String(64), nullable=False),
        _ts("fetched_at", nullable=False),
        sa.Column(
            "ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id"),
    )
    op.create_index("ix_dsm_station_date", "dsm_products", ["station_id", "climate_date"])

    op.drop_index("ix_cli_station_date", table_name="cli_products")
    op.drop_table("cli_products")
    with op.batch_alter_table("stations") as b:
        b.drop_column("dsm_source")
        b.drop_column("cli_location")
