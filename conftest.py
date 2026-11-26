"""Shared pytest fixtures.

DB tests run against TEST_DATABASE_URL (Postgres, used in CI) when it is set,
otherwise against a throwaway SQLite file so the suite runs without a database server.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

# Test helpers shared by the core tests (`import core_fixtures`).
sys.path.insert(0, str(Path(__file__).parent / "packages" / "core" / "tests"))

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.db import make_engine, make_sessionmaker
from edgefront_core.migrate import upgrade


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if os.environ.get("REQUIRE_POSTGRES") and not (url or "").startswith("postgresql"):
        pytest.fail("REQUIRE_POSTGRES is set but TEST_DATABASE_URL is not a Postgres URL")
    if url:
        engine = make_engine(url)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("DROP SCHEMA IF EXISTS auth CASCADE"))  # v2 accounts (0007)
            conn.execute(text("CREATE SCHEMA public"))
        engine.dispose()
    else:
        url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    upgrade("head", database_url=url)
    return url


@pytest.fixture
def engine(db_url: str) -> Iterator[Engine]:
    eng = make_engine(db_url)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return make_sessionmaker(engine)
