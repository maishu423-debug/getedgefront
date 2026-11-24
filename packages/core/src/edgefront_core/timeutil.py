"""Time helpers. All stored times are timezone-aware UTC."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
