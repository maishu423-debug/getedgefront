"""Nightly retention (CONTEXT §9): prune old rows, log row counts and the database size.

- metar_reports, daily_high_events, cli_products, dsm_products: 400 days
- nws_forecasts: latest 3 per station (already enforced by every forecast ingest; checked here)
- model_runs / model_run_stations / model_values: latest 4 runs per model (per office for PFM)
A warning is logged when the database is larger than `DB_SIZE_WARN_BYTES` (default 3 GB of the
5 GB Railway volume).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import Delete, delete, func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import session_scope
from edgefront_core.model_catalog import MODELS
from edgefront_core.model_store import apply_retention
from edgefront_core.models import (
    CliProduct,
    DailyHighEvent,
    DsmProduct,
    MetarReport,
    ModelRun,
    ModelRunStation,
    ModelValue,
    NwsForecast,
    SourceHealth,
    Station,
    StationVenue,
)
from edgefront_core.source_health import record_failure, record_success
from edgefront_core.timeutil import utcnow

log = logging.getLogger("edgefront.retention")
SOURCE = "retention"
KEEP_DAYS = 400
DEFAULT_WARN_BYTES = 3 * 1024**3

COUNTED = (
    Station, StationVenue, MetarReport, DailyHighEvent, CliProduct, DsmProduct, NwsForecast,
    ModelRun, ModelRunStation, ModelValue, SourceHealth,
)  # fmt: skip


@dataclass
class RetentionSummary:
    deleted: dict[str, int] = field(default_factory=dict)
    rows: dict[str, int] = field(default_factory=dict)
    db_bytes: int | None = None
    warn: bool = False


def _rows(s: Session, stmt: Delete) -> int:
    """Rows deleted by a bulk DELETE (rowcount is on the cursor result)."""
    return int(getattr(s.execute(stmt), "rowcount", 0) or 0)


def database_bytes(s: Session) -> int | None:
    bind = s.get_bind()
    if bind.dialect.name == "postgresql":
        return int(s.execute(text("SELECT pg_database_size(current_database())")).scalar_one())
    if bind.dialect.name == "sqlite":
        db = bind.engine.url.database
        return Path(db).stat().st_size if db and Path(db).exists() else None
    return None


def run_retention(
    factory: sessionmaker[Session],
    now: datetime | None = None,
    warn_bytes: int = DEFAULT_WARN_BYTES,
) -> RetentionSummary:
    now = now or utcnow()
    cutoff = now - timedelta(days=KEEP_DAYS)
    out = RetentionSummary()
    try:
        with session_scope(factory) as s:
            old_reports = select(MetarReport.id).where(MetarReport.observed_at < cutoff)
            out.deleted["daily_high_events"] = _rows(
                s,
                delete(DailyHighEvent).where(
                    (DailyHighEvent.observed_at < cutoff)
                    | DailyHighEvent.report_id.in_(old_reports)
                ),
            )
            # corrections that point at a report about to be deleted keep their own row
            s.execute(
                update(MetarReport)
                .where(MetarReport.corrects_report_id.in_(old_reports))
                .values(corrects_report_id=None)
            )
            out.deleted["metar_reports"] = _rows(
                s,
                delete(MetarReport).where(MetarReport.observed_at < cutoff),
            )
            out.deleted["cli_products"] = _rows(
                s,
                delete(CliProduct).where(CliProduct.issued_at < cutoff),
            )
            out.deleted["dsm_products"] = _rows(
                s,
                delete(DsmProduct).where(DsmProduct.issued_at < cutoff),
            )
            runs = 0
            for m in MODELS:
                runs += apply_retention(s, m.id)
            out.deleted["model_runs"] = runs
        with session_scope(factory) as s:
            for model in COUNTED:
                out.rows[model.__tablename__] = int(
                    s.execute(select(func.count()).select_from(model)).scalar_one()
                )
            out.db_bytes = database_bytes(s)
            out.warn = out.db_bytes is not None and out.db_bytes > warn_bytes
            record_success(
                s,
                SOURCE,
                utcnow(),
                notes=f"db {out.db_bytes} bytes; deleted {sum(out.deleted.values())} rows",
            )
    except Exception as exc:
        with session_scope(factory) as s:
            record_failure(s, SOURCE, utcnow(), f"{type(exc).__name__}: {exc}")
        log.exception("retention failed", extra={"source": SOURCE})
        raise
    extra = {
        "source": SOURCE,
        "deleted": out.deleted,
        "rows": out.rows,
        "db_bytes": out.db_bytes,
        "db_mb": round(out.db_bytes / 1e6, 1) if out.db_bytes is not None else None,
        "warn_bytes": warn_bytes,
    }
    if out.warn:
        log.warning("database larger than the warning threshold", extra=extra)
    else:
        log.info("retention", extra=extra)
    return out
