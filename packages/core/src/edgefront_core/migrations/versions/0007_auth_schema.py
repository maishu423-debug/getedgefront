"""v2 Phase 7: Better Auth tables in their own `auth` schema.

The Python side owns every schema change, so Better Auth's tables are created here instead of by
its CLI. The definitions mirror exactly what Better Auth 1.7.28's own migrator generates
(`getMigrations` / `compileMigrations`): table and column names (camelCase, quoted), unique
constraints, foreign keys with ON DELETE CASCADE, and its index names. A drift check
(`apps/web/scripts/auth-schema-check.mjs`, run in CI on Postgres) asks Better Auth itself whether
anything is missing after this migration.

- Postgres: schema `auth`; dates are `timestamptz`, ids `text`, `rateLimit.lastRequest` `bigint`.
- SQLite (local dev/tests only): SQLite has no schemas, so the same tables live in the main
  database; dates use SQLite's `date` type, which Better Auth's SQLite adapter expects.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-26
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUTH_TABLES = ("verification", "account", "session", "rateLimit", "user")  # drop order


def _schema() -> str | None:
    return "auth" if op.get_bind().dialect.name == "postgresql" else None


def _ts() -> sa.types.TypeEngine[Any]:
    return sa.Date().with_variant(postgresql.TIMESTAMP(timezone=True), "postgresql")


def upgrade() -> None:
    schema = _schema()
    if schema:
        op.execute(sa.text('CREATE SCHEMA IF NOT EXISTS "auth"'))
    user_ref = f"{schema}.user.id" if schema else "user.id"

    op.create_table(
        "user",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("emailVerified", sa.Boolean(), nullable=False),
        sa.Column("image", sa.Text(), nullable=True),
        sa.Column("createdAt", _ts(), nullable=False),
        sa.Column("updatedAt", _ts(), nullable=False),
        schema=schema,
    )
    op.create_table(
        "session",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("expiresAt", _ts(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False, unique=True),
        sa.Column("createdAt", _ts(), nullable=False),
        sa.Column("updatedAt", _ts(), nullable=False),
        sa.Column("ipAddress", sa.Text(), nullable=True),
        sa.Column("userAgent", sa.Text(), nullable=True),
        sa.Column("userId", sa.Text(), sa.ForeignKey(user_ref, ondelete="CASCADE"), nullable=False),
        schema=schema,
    )
    op.create_table(
        "account",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("accountId", sa.Text(), nullable=False),
        sa.Column("providerId", sa.Text(), nullable=False),
        sa.Column("userId", sa.Text(), sa.ForeignKey(user_ref, ondelete="CASCADE"), nullable=False),
        sa.Column("accessToken", sa.Text(), nullable=True),
        sa.Column("refreshToken", sa.Text(), nullable=True),
        sa.Column("idToken", sa.Text(), nullable=True),
        sa.Column("accessTokenExpiresAt", _ts(), nullable=True),
        sa.Column("refreshTokenExpiresAt", _ts(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("password", sa.Text(), nullable=True),
        sa.Column("createdAt", _ts(), nullable=False),
        sa.Column("updatedAt", _ts(), nullable=False),
        schema=schema,
    )
    op.create_table(
        "verification",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("expiresAt", _ts(), nullable=False),
        sa.Column("createdAt", _ts(), nullable=False),
        sa.Column("updatedAt", _ts(), nullable=False),
        schema=schema,
    )
    op.create_table(
        "rateLimit",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("key", sa.Text(), nullable=False, unique=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("lastRequest", sa.BigInteger(), nullable=False),
        schema=schema,
    )
    op.create_index("session_userId_idx", "session", ["userId"], schema=schema)
    op.create_index("account_userId_idx", "account", ["userId"], schema=schema)
    op.create_index("verification_identifier_idx", "verification", ["identifier"], schema=schema)


def downgrade() -> None:
    schema = _schema()
    op.drop_index("verification_identifier_idx", table_name="verification", schema=schema)
    op.drop_index("account_userId_idx", table_name="account", schema=schema)
    op.drop_index("session_userId_idx", table_name="session", schema=schema)
    for t in AUTH_TABLES:
        op.drop_table(t, schema=schema)
    if schema:
        op.execute(sa.text('DROP SCHEMA IF EXISTS "auth"'))
