from __future__ import annotations

import json
import logging

import pytest

from edgefront_core.logs import JsonFormatter
from edgefront_core.settings import Settings


def test_json_formatter_includes_extra_fields() -> None:
    record = logging.LogRecord("worker", logging.INFO, __file__, 1, "heartbeat", None, None)
    record.source = "worker"
    record.duration_ms = 12
    out = json.loads(JsonFormatter().format(record))
    assert out["msg"] == "heartbeat"
    assert out["level"] == "INFO"
    assert out["source"] == "worker"
    assert out["duration_ms"] == 12
    assert out["ts"].endswith("+00:00")


def test_user_agent_uses_contact_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTACT_EMAIL", "ops@example.org")
    s = Settings(_env_file=None)
    assert s.user_agent == "EdgeFront/1.0 (getedgefront.com; ops@example.org)"
