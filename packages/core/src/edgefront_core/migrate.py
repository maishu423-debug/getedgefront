"""Apply Alembic migrations: `python -m edgefront_core.migrate [revision]` (default: head)."""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from edgefront_core.settings import get_settings


def alembic_config(database_url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    # ConfigParser treats % as interpolation; escape it for passwords containing %.
    url = database_url or get_settings().database_url
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def upgrade(revision: str = "head", database_url: str | None = None) -> None:
    command.upgrade(alembic_config(database_url), revision)


def main() -> None:
    upgrade(sys.argv[1] if len(sys.argv) > 1 else "head")


if __name__ == "__main__":
    main()
