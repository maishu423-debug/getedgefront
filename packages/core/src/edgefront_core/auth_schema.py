"""Tables owned by the Next.js app, not by SQLAlchemy models:

- Better Auth's tables (v2 Phase 7, migration 0007), schema `auth`;
- the Stripe billing mirror (v2 Phase 8, migration 0008), schema `billing`.

Alembic creates them, but they have no models, so model/migration comparisons skip them. On
Postgres they live in their own schemas; on SQLite (local only) in the main database.
"""

from __future__ import annotations

from typing import Any

AUTH_SCHEMA = "auth"
AUTH_TABLES = frozenset({"user", "session", "account", "verification", "rateLimit"})
AUTH_INDEXES = frozenset(
    {"session_userId_idx", "account_userId_idx", "verification_identifier_idx"}
)
BILLING_SCHEMA = "billing"
BILLING_TABLES = frozenset({"customers", "subscriptions", "webhook_events"})
BILLING_INDEXES = frozenset({"subscriptions_user_id_idx"})

WEB_SCHEMAS = frozenset({AUTH_SCHEMA, BILLING_SCHEMA})
WEB_TABLES = AUTH_TABLES | BILLING_TABLES
WEB_INDEXES = AUTH_INDEXES | BILLING_INDEXES


def is_auth_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """True for the web app's tables and indexes (auth and billing)."""
    if type_ == "table":
        return getattr(obj, "schema", None) in WEB_SCHEMAS or name in WEB_TABLES
    if type_ == "index":
        table = getattr(obj, "table", None)
        return name in WEB_INDEXES or (table is not None and table.name in WEB_TABLES)
    return False


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """Alembic `include_object`: leave the web app's tables out of model comparisons."""
    return not is_auth_object(obj, name, type_, reflected, compare_to)
