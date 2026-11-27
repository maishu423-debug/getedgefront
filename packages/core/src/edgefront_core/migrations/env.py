"""Alembic environment. Run via `python -m edgefront_core.migrate` (no alembic.ini needed)."""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection

from edgefront_core.auth_schema import include_object
from edgefront_core.db import make_engine
from edgefront_core.models import Base

config = context.config
target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,  # Better Auth's tables are not ORM models
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if url is None:
        raise RuntimeError("sqlalchemy.url must be set by edgefront_core.migrate")
    engine = make_engine(url)
    with engine.connect() as connection:
        _run(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
