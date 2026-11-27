"""Weekly check that each station still measures in the unit the registry says (v2 Phase 9, Q36).

An ASOS station measures whole °F, so every METAR T-group value it sends converts back to within
±0.09 °F of a whole °F (the tenths °C is a conversion). A station measuring in °C (KBKF) matches
that only by chance (~18 % of values). If a station's last 7 days disagree with
`stations.native_temp_unit`, we log a warning: the registry (and the `f_possible` readings built on
it) may need updating. Nothing is changed automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from edgefront_core.models import MetarReport, Station
from edgefront_core.units import c_to_f

log = logging.getLogger("edgefront.native_unit_check")

NEAR = Decimal("0.09")
F_MIN_SHARE = 0.95  # an °F station: (nearly) every T-group value sits on a whole °F
C_MAX_SHARE = 0.50  # a °C station: about 18 % by chance; well over half means it changed
MIN_REPORTS = 50


def near_whole_f(c: Decimal) -> bool:
    f = c_to_f(c)
    return abs(f - f.to_integral_value()) <= NEAR


@dataclass(frozen=True)
class UnitCheck:
    station_id: str
    registry_unit: str
    reports: int
    near_whole_f: int
    verdict: Literal["ok", "drift", "too_few"]

    @property
    def share(self) -> float:
        return self.near_whole_f / self.reports if self.reports else 0.0


def judge(registry_unit: str, reports: int, near: int) -> Literal["ok", "drift", "too_few"]:
    if reports < MIN_REPORTS:
        return "too_few"
    share = near / reports
    if registry_unit == "C":
        return "ok" if share <= C_MAX_SHARE else "drift"
    return "ok" if share >= F_MIN_SHARE else "drift"


def check_native_units(session: Session, now: datetime, days: int = 7) -> list[UnitCheck]:
    since = now - timedelta(days=days)
    units = dict(session.execute(select(Station.id, Station.native_temp_unit)).tuples().all())
    counts: dict[str, list[int]] = {sid: [0, 0] for sid in units}
    rows = session.execute(
        select(MetarReport.station_id, MetarReport.temp_c).where(
            MetarReport.observed_at >= since,
            MetarReport.temp_precision == "tenths",
            MetarReport.temp_c.is_not(None),
        )
    )
    for sid, temp_c in rows:
        if sid in counts and temp_c is not None:
            counts[sid][0] += 1
            counts[sid][1] += near_whole_f(Decimal(temp_c))
    return [
        UnitCheck(sid, units[sid], n, k, judge(units[sid], n, k))
        for sid, (n, k) in sorted(counts.items())
    ]


def run_native_unit_check(factory: sessionmaker[Session], now: datetime) -> list[UnitCheck]:
    with factory() as session:
        results = check_native_units(session, now)
    for r in results:
        if r.verdict == "drift":
            log.warning(
                "station measuring unit may have changed: check stations.yaml native_temp_unit",
                extra={"station": r.station_id, "registry_unit": r.registry_unit,
                       "near_whole_f_share": round(r.share, 3), "reports": r.reports},
            )  # fmt: skip
    log.info(
        "native unit check",
        extra={"ok": sum(r.verdict == "ok" for r in results),
               "drift": sum(r.verdict == "drift" for r in results),
               "too_few": sum(r.verdict == "too_few" for r in results)},
    )  # fmt: skip
    return results
