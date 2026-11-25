"""The api service's pre-deploy command: migrations + seed, safe to run on every deploy."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select, text

from edgefront_core import db, settings
from edgefront_core.models import Station


def test_deploy_db_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"sqlite:///{tmp_path / 'deploy.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    settings.get_settings.cache_clear()
    db.get_engine.cache_clear()
    try:
        from edgefront_core.deploy_db import main

        main()
        main()  # second deploy: nothing to do, no error
        eng = create_engine(url)
        with eng.connect() as c:
            assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert c.execute(select(func.count()).select_from(Station)).scalar_one() == 28
        eng.dispose()
    finally:
        settings.get_settings.cache_clear()
        db.get_engine.cache_clear()
