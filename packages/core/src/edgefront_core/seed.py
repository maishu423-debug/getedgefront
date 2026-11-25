"""Idempotent upsert of data/stations.yaml into `stations` + `station_venues`.

    python -m edgefront_core.seed [path/to/stations.yaml]

Rules:
- Station display fields (name, city, state, tz, day_basis) come from the YAML.
- dsm_location / pfm_point: a null in the YAML never overwrites a value already stored.
- dsm_source / cli_location: always taken from the YAML (owner decisions), nulls included.
- Enrichment fields (lat/lon/elevation/office/grid/official_name) are never touched here.
- Venues: the YAML is the full truth per station; DB rows not in the YAML are deleted.
- Stations missing from the YAML are marked inactive (never deleted: they own observations).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from edgefront_core.db import get_engine, make_sessionmaker, session_scope
from edgefront_core.models import Station, StationVenue
from edgefront_core.registry import StationEntry, load_registry, registry_path


@dataclass
class SeedResult:
    stations_inserted: list[str] = field(default_factory=list)
    stations_updated: list[str] = field(default_factory=list)
    stations_deactivated: list[str] = field(default_factory=list)
    venues_inserted: int = 0
    venues_updated: int = 0
    venues_deleted: int = 0
    unverified_venues: int = 0

    @property
    def changed(self) -> bool:
        return bool(
            self.stations_inserted
            or self.stations_updated
            or self.stations_deactivated
            or self.venues_inserted
            or self.venues_updated
            or self.venues_deleted
        )


def _apply(obj: object, values: dict[str, object]) -> bool:
    changed = False
    for k, v in values.items():
        if getattr(obj, k) != v:
            setattr(obj, k, v)
            changed = True
    return changed


def _station_values(e: StationEntry) -> dict[str, object]:
    values: dict[str, object] = {
        "name": e.name,
        "city": e.city,
        "state": e.state,
        "tz": e.tz,
        "day_basis": e.day_basis,
        "active": True,
        # Source choices are owner decisions: the YAML is authoritative, nulls included.
        "dsm_source": e.dsm_source,
        "aliases": list(e.aliases),
        "cli_location": e.cli_location,
    }
    if e.dsm_location is not None:
        values["dsm_location"] = e.dsm_location
    if e.pfm_point is not None:
        values["pfm_point"] = e.pfm_point
    return values


def seed(session: Session, entries: list[StationEntry]) -> SeedResult:
    res = SeedResult()
    existing = {s.id: s for s in session.scalars(select(Station))}

    for e in entries:
        st = existing.get(e.id)
        if st is None:
            session.add(Station(id=e.id, **_station_values(e)))
            res.stations_inserted.append(e.id)
        elif _apply(st, _station_values(e)):
            res.stations_updated.append(e.id)

        current = {
            (v.venue, v.market_kind): v
            for v in session.scalars(select(StationVenue).where(StationVenue.station_id == e.id))
        }
        wanted = set()
        for v in e.venues:
            wanted.add((v.venue, v.kind))
            if not v.verified:
                res.unverified_venues += 1
            vals: dict[str, object] = {
                "market": v.market,
                "settlement_source": v.settlement_source,
                "rules_url": v.rules_url,
                "verified": v.verified,
                "verified_at": v.verified_at,
            }
            row = current.get((v.venue, v.kind))
            if row is None:
                session.add(
                    StationVenue(station_id=e.id, venue=v.venue, market_kind=v.kind, **vals)
                )
                res.venues_inserted += 1
            elif _apply(row, vals):
                res.venues_updated += 1
        for key, row in current.items():
            if key not in wanted:
                session.delete(row)
                res.venues_deleted += 1
        session.flush()

    yaml_ids = {e.id for e in entries}
    for sid, st in existing.items():
        if sid not in yaml_ids and st.active:
            st.active = False
            res.stations_deactivated.append(sid)
    return res


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    path = Path(args[0]) if args else registry_path()
    entries = load_registry(path)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    factory = make_sessionmaker(get_engine())
    with session_scope(factory) as s:
        res = seed(s, entries)
    out = sys.stdout
    out.write(f"seed: {len(entries)} stations in {path}\n")
    out.write(f"  stations inserted:    {len(res.stations_inserted)} {res.stations_inserted}\n")
    out.write(f"  stations updated:     {len(res.stations_updated)} {res.stations_updated}\n")
    out.write(
        f"  stations deactivated: {len(res.stations_deactivated)} {res.stations_deactivated}\n"
    )
    out.write(
        f"  venues inserted/updated/deleted: "
        f"{res.venues_inserted}/{res.venues_updated}/{res.venues_deleted}\n"
    )
    out.write(f"  UNVERIFIED venue mappings: {res.unverified_venues}\n")
    out.write("  result: " + ("changes applied\n" if res.changed else "no changes (idempotent)\n"))


if __name__ == "__main__":
    main()
