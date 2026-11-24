"""The migrated schema must match the ORM models (catches drift between models.py and Alembic)."""

from __future__ import annotations

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from edgefront_core.migrate import alembic_config, upgrade
from edgefront_core.models import Base

EXPECTED_TABLES = {
    "stations",
    "station_venues",
    "metar_reports",
    "daily_high_events",
    "dsm_products",
    "nws_forecasts",
    "model_runs",
    "model_values",
    "source_health",
}


def test_all_v1_tables_exist_and_no_hf_observations(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert tables == EXPECTED_TABLES
    assert "hf_observations" not in tables  # Premium (v2), never in v1


def test_migrations_match_models(engine: Engine) -> None:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": False})
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == []


def test_downgrade_then_upgrade(db_url: str, engine: Engine) -> None:
    command.downgrade(alembic_config(db_url), "0001")
    assert set(inspect(engine).get_table_names()) == {"alembic_version", "source_health"}
    upgrade("head", database_url=db_url)
    assert "stations" in inspect(engine).get_table_names()
