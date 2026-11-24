"""Phase 0 bootstrap: source_health only (the rest of §7 arrives in Phase 1).

Revision ID: 0001
Revises:
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_health",
        sa.Column("source", sa.String(64), primary_key=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("last_item_time", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("source_health")
