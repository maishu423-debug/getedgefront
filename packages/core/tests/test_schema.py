"""The migrated schema must match the ORM models (catches drift between models.py and Alembic)."""

from __future__ import annotations

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from edgefront_core.auth_schema import AUTH_TABLES, BILLING_TABLES, include_object
from edgefront_core.migrate import alembic_config, upgrade
from edgefront_core.models import Base

EXPECTED_TABLES = {
    "stations",
    "cli_products",
    "station_venues",
    "metar_reports",
    "daily_high_events",
    "dsm_products",
    "nws_forecasts",
    "model_runs",
    "model_values",
    "model_run_stations",
    "source_health",
    "hf_observations",  # v2 Phase 9
    "hf_files",
}


def test_all_tables_exist(engine: Engine) -> None:
    insp = inspect(engine)
    tables = set(insp.get_table_names()) - {"alembic_version"}
    if engine.dialect.name == "postgresql":
        assert tables == EXPECTED_TABLES
        assert set(insp.get_table_names(schema="auth")) == AUTH_TABLES  # Better Auth, own schema
        assert set(insp.get_table_names(schema="billing")) == BILLING_TABLES  # Stripe mirror
    else:  # SQLite has no schemas: the web app's tables sit next to ours
        assert tables == EXPECTED_TABLES | AUTH_TABLES | BILLING_TABLES


def test_migrations_match_models(engine: Engine) -> None:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(
            conn, opts={"compare_type": False, "include_object": include_object}
        )
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == []


def test_downgrade_then_upgrade(db_url: str, engine: Engine) -> None:
    command.downgrade(alembic_config(db_url), "0001")
    assert set(inspect(engine).get_table_names()) == {"alembic_version", "source_health"}
    upgrade("head", database_url=db_url)
    assert "stations" in inspect(engine).get_table_names()
