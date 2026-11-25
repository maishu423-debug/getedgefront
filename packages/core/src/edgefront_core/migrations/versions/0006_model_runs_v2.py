"""Phase 5: model runs keyed by id (model, cycle, issuer), per-station run rows, native units.

The Phase 1 model tables were never written to, so they are dropped and recreated.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BIGID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.drop_index("ix_model_values_station", table_name="model_values")
    op.drop_table("model_values")
    op.drop_table("model_runs")

    op.create_table(
        "model_runs",
        sa.Column("id", BIGID, autoincrement=True, nullable=False),
        sa.Column("model", sa.String(length=16), nullable=False),
        sa.Column("cycle_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issuer", sa.String(length=8), server_default="", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="partial", nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("steps_expected", sa.Integer(), nullable=True),
        sa.Column("steps_fetched", sa.Integer(), server_default="0", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('partial', 'complete', 'failed')", name="ck_model_runs_status"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model", "cycle_time", "issuer", name="uq_model_runs_key"),
    )
    op.create_index("ix_model_runs_model_cycle", "model_runs", ["model", "cycle_time"])
    op.create_table(
        "model_run_stations",
        sa.Column("run_id", BIGID, nullable=False),
        sa.Column("station_id", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("point_name", sa.String(length=160), nullable=True),
        sa.Column("grid_lat", sa.Float(), nullable=True),
        sa.Column("grid_lon", sa.Float(), nullable=True),
        sa.Column("grid_distance_km", sa.Float(), nullable=True),
        sa.Column("height_m", sa.Float(), nullable=True),
        sa.Column("land_fraction", sa.Float(), nullable=True),
        sa.CheckConstraint(
            "status IN ('ok', 'not_available', 'failed')", name="ck_model_run_stations_status"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["model_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.PrimaryKeyConstraint("run_id", "station_id"),
    )
    op.create_table(
        "model_values",
        sa.Column("run_id", BIGID, nullable=False),
        sa.Column("station_id", sa.String(length=8), nullable=False),
        sa.Column("valid_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("variable", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("native_value", sa.Float(), nullable=True),
        sa.Column("native_unit", sa.String(length=16), nullable=True),
        sa.Column("category", sa.String(length=4), nullable=True),
        sa.Column("is_computed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["model_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.PrimaryKeyConstraint("run_id", "station_id", "valid_time", "variable"),
    )
    op.create_index("ix_model_values_station", "model_values", ["station_id", "run_id"])


def downgrade() -> None:
    op.drop_index("ix_model_values_station", table_name="model_values")
    op.drop_table("model_values")
    op.drop_table("model_run_stations")
    op.drop_index("ix_model_runs_model_cycle", table_name="model_runs")
    op.drop_table("model_runs")

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
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.PrimaryKeyConstraint("model", "cycle_time", "station_id", "valid_time", "variable"),
    )
    op.create_index(
        "ix_model_values_station", "model_values", ["station_id", "model", "cycle_time"]
    )
