"""v2 Phase 8: billing tables in their own `billing` schema (Stripe mirror).

Owned by the Next.js app (no SQLAlchemy models; model comparisons skip them, like `auth`). We
never store card data: only Stripe ids, statuses and dates.

- `customers`: one Stripe customer per user (created once, reused) + `trial_used_at` (one trial
  per account; set when a trialing subscription is first mirrored).
- `subscriptions`: the user's subscriptions as Stripe last reported them. Webhooks re-fetch the
  subscription and overwrite the row, so event order doesn't matter.
- `webhook_events`: every Stripe event id seen, for idempotency and debugging.

Rows of a deleted account go with it (FK to auth."user" ON DELETE CASCADE); the Stripe customer
itself is kept in Stripe for invoices.

- Postgres: schema `billing`, `timestamptz`, `boolean`.
- SQLite (local dev/tests only): no schemas, same table names in the main database; times are
  ISO-8601 text and booleans 0/1 (the web app normalises both).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-27
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BILLING_TABLES = ("webhook_events", "subscriptions", "customers")  # drop order


def _pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _ts() -> sa.types.TypeEngine[Any]:
    return sa.Text().with_variant(postgresql.TIMESTAMP(timezone=True), "postgresql")


def upgrade() -> None:
    pg = _pg()
    schema = "billing" if pg else None
    user_ref = "auth.user.id" if pg else "user.id"
    if pg:
        op.execute(sa.text('CREATE SCHEMA IF NOT EXISTS "billing"'))
    false = sa.text("false") if pg else sa.text("0")

    op.create_table(
        "customers",
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey(user_ref, ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("stripe_customer_id", sa.Text(), nullable=False, unique=True),
        sa.Column("trial_used_at", _ts(), nullable=True),
        sa.Column("created_at", _ts(), nullable=False),
        schema=schema,
    )
    op.create_table(
        "subscriptions",
        sa.Column("stripe_subscription_id", sa.Text(), primary_key=True),
        sa.Column(
            "user_id", sa.Text(), sa.ForeignKey(user_ref, ondelete="CASCADE"), nullable=False
        ),
        sa.Column("stripe_customer_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("price_id", sa.Text(), nullable=True),
        sa.Column("current_period_end", _ts(), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=false),
        sa.Column("cancel_at", _ts(), nullable=True),
        sa.Column("trial_end", _ts(), nullable=True),
        sa.Column("canceled_at", _ts(), nullable=True),
        sa.Column("ended_at", _ts(), nullable=True),
        sa.Column("latest_invoice_status", sa.Text(), nullable=True),
        sa.Column("updated_from_event_id", sa.Text(), nullable=True),
        sa.Column("updated_at", _ts(), nullable=False),
        schema=schema,
    )
    op.create_index("subscriptions_user_id_idx", "subscriptions", ["user_id"], schema=schema)
    op.create_table(
        "webhook_events",
        sa.Column("stripe_event_id", sa.Text(), primary_key=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("received_at", _ts(), nullable=False),
        sa.Column("processed_at", _ts(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        schema=schema,
    )


def downgrade() -> None:
    schema = "billing" if _pg() else None
    op.drop_index("subscriptions_user_id_idx", table_name="subscriptions", schema=schema)
    for t in BILLING_TABLES:
        op.drop_table(t, schema=schema)
    if schema:
        op.execute(sa.text('DROP SCHEMA IF EXISTS "billing"'))
