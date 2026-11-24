"""Pydantic response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: Literal["api"] = "api"
    db: Literal["ok", "unreachable"]
    generated_at: datetime
