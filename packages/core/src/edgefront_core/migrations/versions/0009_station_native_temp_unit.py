"""v2 Phase 9 (B9, Q36): stations.native_temp_unit — the unit the station measures in.

ASOS stations measure in whole °F; their METAR tenths °C is a conversion (Q36: 27 of 28 stations,
every T-group value within ±0.09 °F of a whole °F). KBKF (military) measures in °C. The value
decides whether a temperature has `f_possible` readings; a weekly check warns if data drift.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stations",
        sa.Column("native_temp_unit", sa.String(1), nullable=False, server_default="F"),
    )


def downgrade() -> None:
    with op.batch_alter_table("stations") as b:
        b.drop_column("native_temp_unit")
