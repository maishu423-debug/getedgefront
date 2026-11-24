"""Ingest sources known to the status strip, with their schedules (CONTEXT.md §6.4)."""

from __future__ import annotations

from dataclasses import dataclass

from edgefront_core.settings import Settings


@dataclass(frozen=True)
class SourceInfo:
    key: str
    label: str
    producer: str
    schedule_seconds: int

    @property
    def unhealthy_after_seconds(self) -> int:
        # A source is unhealthy if its last success is older than 3x its schedule.
        return 3 * self.schedule_seconds


def known_sources(settings: Settings) -> list[SourceInfo]:
    """Sources that exist in this phase. Later phases append DSM, NWS forecast and models."""
    return [
        SourceInfo(
            "metar", "Hourly METAR + SPECI", "NOAA Aviation Weather Center",
            settings.metar_poll_seconds,
        ),
        SourceInfo("worker", "Ingest worker", "EdgeFront", settings.heartbeat_seconds),
    ]  # fmt: skip
