"""Database engine and session helpers (SQLAlchemy 2 + psycopg 3)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.settings import get_settings


def make_engine(url: str) -> Engine:
    connect_args: dict[str, object] = {}
    if url.startswith("postgresql"):
        # Fail fast instead of hanging when the DB is unreachable.
        connect_args["connect_timeout"] = 5
        # timestamptz values come back in the *session* time zone; pin it to UTC so every
        # datetime we read is UTC regardless of the server's default.
        connect_args["options"] = "-c timezone=UTC"
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return make_engine(get_settings().database_url)


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on error."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping(engine: Engine) -> None:
    """Raise if the database can't answer a trivial query."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
