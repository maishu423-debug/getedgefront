"""Apply Alembic migrations.

python -m edgefront_core.migrate            # upgrade to head
python -m edgefront_core.migrate down base  # downgrade (CI runs up → down → up on Postgres)
"""

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


def downgrade(revision: str, database_url: str | None = None) -> None:
    command.downgrade(alembic_config(database_url), revision)


def main(argv: list[str] | None = None) -> None:
    """`migrate` | `migrate <rev>` (upgrade) | `migrate up [rev]` | `migrate down <rev|base>`."""
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "down":
        if len(args) < 2:
            raise SystemExit("usage: python -m edgefront_core.migrate down <revision|base>")
        downgrade(args[1])
    elif args and args[0] == "up":
        upgrade(args[1] if len(args) > 1 else "head")
    else:
        upgrade(args[0] if args else "head")


if __name__ == "__main__":
    main()
