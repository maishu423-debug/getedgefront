"""Store "no value" in JSON columns as SQL NULL instead of the JSON literal 'null'.

Rows written before this fix kept JSON 'null' (e.g. decode_errors), which made
`decode_errors IS NOT NULL` match every product. Schema is unchanged; data only.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = [
    ("cli_products", "decode_errors"),
    ("dsm_products", "decode_errors"),
    ("metar_reports", "sky"),
    ("nws_forecasts", "periods"),
    ("nws_forecasts", "hourly"),
    ("stations", "aliases"),
]


def upgrade() -> None:
    pg = op.get_bind().dialect.name == "postgresql"
    for table, col in COLUMNS:
        cond = f"{col} = 'null'::jsonb" if pg else f"{col} = 'null'"
        op.execute(f"UPDATE {table} SET {col} = NULL WHERE {cond}")  # noqa: S608


def downgrade() -> None:
    pass  # SQL NULL is the correct representation; nothing to restore.
