"""Runtime settings, read from environment variables (see CONTEXT.md §13 and .env.example)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://edgefront:edgefront@localhost:5432/edgefront"

    # Used in the NWS/NOAA User-Agent. Owner must supply it before any upstream fetch (Q1).
    contact_email: str = ""

    metar_poll_seconds: int = 180
    dsm_poll_seconds: int = 720  # 12 min: polite to IEM (owner: 10-15 min)
    cli_poll_seconds: int = 900
    forecast_poll_seconds: int = 1800
    model_poll_seconds: int = 900
    stale_metar_minutes: int = 90

    heartbeat_seconds: int = 60
    # CI's Docker smoke test runs the worker with upstream jobs off (no CONTACT_EMAIL there, and
    # CI must never contact NOAA/NWS/IEM). Always true in deployed environments.
    worker_upstream_enabled: bool = True

    @property
    def user_agent(self) -> str:
        """User-Agent for every NWS/NOAA request (CONTEXT.md §4)."""
        return f"EdgeFront/1.0 (getedgefront.com; {self.contact_email})"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
