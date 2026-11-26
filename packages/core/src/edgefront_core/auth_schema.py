"""Better Auth's tables (v2 Phase 7). Created by Alembic migration 0007 but owned by the
Next.js app (Better Auth): they have no SQLAlchemy models, and model/migration comparisons skip
them. On Postgres they live in schema `auth`; on SQLite (local only) in the main database."""

from __future__ import annotations

from typing import Any

AUTH_SCHEMA = "auth"
AUTH_TABLES = frozenset({"user", "session", "account", "verification", "rateLimit"})
AUTH_INDEXES = frozenset(
    {"session_userId_idx", "account_userId_idx", "verification_identifier_idx"}
)


def is_auth_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """True for Better Auth's tables and indexes."""
    if type_ == "table":
        return getattr(obj, "schema", None) == AUTH_SCHEMA or name in AUTH_TABLES
    if type_ == "index":
        table = getattr(obj, "table", None)
        return name in AUTH_INDEXES or (table is not None and table.name in AUTH_TABLES)
    return False


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """Alembic `include_object`: leave Better Auth's tables out of model comparisons."""
    return not is_auth_object(obj, name, type_, reflected, compare_to)
