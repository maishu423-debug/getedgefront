"""Capture real PFM products (api.weather.gov) as test fixtures.

    DATABASE_URL=... uv run python tools/capture_pfm.py [--cycles N] [--offices OKX FWD ...]

Takes the offices of every registry station with a `pfm_point` (from the database, filled by
enrich_stations), saves the newest N products per office verbatim to
packages/core/tests/fixtures/nws_pfm/PFM{office}_{issued}.json and appends URL + UTC fetch time
to that folder's README.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from edgefront_core.db import get_engine, make_sessionmaker, session_scope
from edgefront_core.http import get_with_retry, make_client
from edgefront_core.models import Station
from edgefront_core.timeutil import utcnow

OUT = Path(__file__).resolve().parents[1] / "packages" / "core" / "tests" / "fixtures" / "nws_pfm"
NWS = "https://api.weather.gov"
LD = {"Accept": "application/ld+json"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cycles", type=int, default=1)
    p.add_argument("--offices", nargs="*")
    a = p.parse_args()
    offices = a.offices
    if not offices:
        with session_scope(make_sessionmaker(get_engine())) as s:
            offices = sorted(
                {
                    o
                    for (o,) in s.execute(
                        select(Station.nws_office).where(Station.pfm_point.is_not(None))
                    )
                    if o
                }
            )
    OUT.mkdir(parents=True, exist_ok=True)
    readme = OUT / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Fixtures: nws_pfm\n\nReal Point Forecast Matrices from api.weather.gov, saved "
            "verbatim. Requests sent with the EdgeFront User-Agent (CONTEXT.md §4).\n\n"
            "| File | URL | Fetched (UTC) | HTTP |\n|---|---|---|---|\n",
            encoding="utf-8",
            newline="\n",
        )
    with make_client(timeout=30) as c:
        for office in offices:
            listing = get_with_retry(c, f"{NWS}/products/types/PFM/locations/{office}", headers=LD)
            graph = (listing.json() or {}).get("@graph") or []
            for item in graph[: a.cycles]:
                url = f"{NWS}/products/{item['id']}"
                fetched = utcnow()
                r = get_with_retry(c, url, headers=LD)
                r.raise_for_status()
                issued = "".join(ch for ch in item["issuanceTime"][:16] if ch.isdigit())
                name = f"PFM{office}_{issued}.json"
                if (OUT / name).exists():
                    continue
                (OUT / name).write_bytes(r.content)
                with readme.open("a", encoding="utf-8", newline="\n") as f:
                    f.write(
                        f"| `{name}` | {url} | {fetched.strftime('%Y-%m-%dT%H:%M:%SZ')} "
                        f"| {r.status_code} |\n"
                    )
                print(name, len(r.content))


if __name__ == "__main__":
    main()
