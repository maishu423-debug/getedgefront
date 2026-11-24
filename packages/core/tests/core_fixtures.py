from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_path(rel: str) -> Path:
    return FIXTURES / rel


def load_json(rel: str) -> Any:
    return json.loads(fixture_path(rel).read_text(encoding="utf-8"))


def product_text(rel: str) -> str:
    text: str = load_json(rel)["productText"]
    return text
