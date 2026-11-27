"""v2 Phase 9 B4: 5-minute HFMETAR data (hf_observations) and the processed-file log (hf_files).

Primary key (station_id, observed_at) also serves "latest first" queries (Postgres scans the
index backwards). Retention 7 days (nightly job).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    ts = sa.DateTime(timezone=True)
    op.create_table(
        "hf_observations",
        sa.Column(
            "station_id",
            sa.String(8),
            sa.ForeignKey("stations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("observed_at", ts, nullable=False),
        sa.Column("temp_c", sa.Numeric(5, 2), nullable=True),
        sa.Column("temp_precision", sa.String(8), nullable=True),
        sa.Column("dewpt_c", sa.Numeric(5, 2), nullable=True),
        sa.Column("wind_dir_deg", sa.Integer(), nullable=True),
        sa.Column("wind_kt", sa.Integer(), nullable=True),
        sa.Column("gust_kt", sa.Integer(), nullable=True),
        sa.Column("altim_inhg", sa.Numeric(5, 2), nullable=True),
        sa.Column("vis_mi", sa.Numeric(7, 4), nullable=True),
        sa.Column("precip_in", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "qc",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("source_file", sa.String(40), nullable=False),
        sa.Column("received_at", ts, nullable=True),
        sa.Column("file_modified_at", ts, nullable=True),
        sa.Column("fetched_at", ts, nullable=False),
        sa.Column("ingested_at", ts, nullable=False),
        sa.Column("updated_at", ts, nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("backfill", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("station_id", "observed_at"),
    )
    op.create_table(
        "hf_files",
        sa.Column("name", sa.String(40), primary_key=True),
        sa.Column("modified_at", ts, nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("processed_at", ts, nullable=False),
        sa.Column("records", sa.Integer(), nullable=False),
        sa.Column("our_rows", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("hf_files")
    op.drop_table("hf_observations")
