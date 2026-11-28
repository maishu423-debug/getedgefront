"""backup.py helpers: libpq URL and the 14-daily / 8-weekly pruning (no network, no Postgres)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


def _load() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "backup.py"
    spec = importlib.util.spec_from_file_location("edgefront_backup", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


backup = _load()


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgresql+psycopg://u:p@h:5432/db", "postgresql://u:p@h:5432/db"),
        ("postgres://u:p@h/db", "postgresql://u:p@h/db"),
        ("postgresql://u:p@h/db", "postgresql://u:p@h/db"),
    ],
)
def test_pg_url(given: str, expected: str) -> None:
    assert backup.pg_url(given) == expected


@pytest.mark.parametrize(
    ("endpoint", "region", "expected"),
    [
        ("https://s3.us-east-1.amazonaws.com", "auto", "us-east-1"),  # AWS (owner's choice)
        ("https://s3-us-east-2.amazonaws.com/", "auto", "us-east-2"),
        ("https://s3.us-east-1.amazonaws.com", "us-east-1", "us-east-1"),
        ("https://abc123.r2.cloudflarestorage.com", "auto", "auto"),  # R2 signs with "auto"
        ("https://s3.us-west-004.backblazeb2.com", "us-west-004", "us-west-004"),
    ],
)
def test_s3_region(endpoint: str, region: str, expected: str) -> None:
    assert backup.s3_region(endpoint, region) == expected


class FakeS3:
    def __init__(self, keys: list[str]) -> None:
        self.keys = set(keys)

    def get_paginator(self, _name: str) -> Any:
        outer = self

        class P:
            def paginate(self, Bucket: str, Prefix: str) -> list[dict[str, Any]]:  # noqa: N803
                return [
                    {"Contents": [{"Key": k} for k in sorted(outer.keys) if k.startswith(Prefix)]}
                ]

        return P()

    def delete_object(self, Bucket: str, Key: str) -> None:  # noqa: N803
        self.keys.remove(Key)


def test_prune_keeps_the_newest() -> None:
    days = [f"edgefront/daily/edgefront-202611{d:02d}T070000Z.dump" for d in range(1, 21)]
    weeks = [f"edgefront/weekly/edgefront-2026{m:02d}01T070000Z.dump" for m in range(1, 11)]
    s3 = FakeS3(days + weeks)
    gone = backup.prune(s3, "b", "edgefront/daily/", 14)
    assert len(gone) == 6
    assert max(gone) < min(k for k in s3.keys if "/daily/" in k)  # only the oldest went
    backup.prune(s3, "b", "edgefront/weekly/", 8)
    assert len([k for k in s3.keys if "/weekly/" in k]) == 8
    assert len([k for k in s3.keys if "/daily/" in k]) == 14
