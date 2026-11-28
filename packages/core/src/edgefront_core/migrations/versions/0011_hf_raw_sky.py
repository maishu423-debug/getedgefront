"""v2 Phase 10b: raw record, sky layers and present weather on hf_observations.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("hf_observations", sa.Column("raw_message", sa.Text(), nullable=True))
    op.add_column(
        "hf_observations",
        sa.Column(
            "sky",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )
    op.add_column("hf_observations", sa.Column("pres_wx", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("hf_observations", "pres_wx")
    op.drop_column("hf_observations", "sky")
    op.drop_column("hf_observations", "raw_message")
