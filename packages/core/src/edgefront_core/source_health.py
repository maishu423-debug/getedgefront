"""Read/write helpers for the `source_health` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from edgefront_core.models import SourceHealth


def _get_or_create(session: Session, source: str) -> SourceHealth:
    row = session.get(SourceHealth, source)
    if row is None:
        row = SourceHealth(source=source)
        session.add(row)
    return row


def record_success(
    session: Session,
    source: str,
    at: datetime,
    *,
    last_item_time: datetime | None = None,
    notes: str | None = None,
) -> SourceHealth:
    row = _get_or_create(session, source)
    row.last_attempt_at = at
    row.last_success_at = at
    if last_item_time is not None:
        row.last_item_time = last_item_time
    if notes is not None:
        row.notes = notes
    return row


def record_failure(session: Session, source: str, at: datetime, error: str) -> SourceHealth:
    row = _get_or_create(session, source)
    row.last_attempt_at = at
    row.last_error_at = at
    row.last_error = error[:2000]
    return row
