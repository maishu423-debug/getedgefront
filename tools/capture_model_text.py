"""Capture real NOMADS model text bulletins (NBH, NBS, MAV, LAV) as test fixtures.

    uv run python tools/capture_model_text.py nbh 2026112512 [more cycles...]

Each bulletin holds ~2,000-9,000 station blocks (up to 28 MB), so only the blocks for the
registry stations (plus any extra ids given with --extra) are kept. Blocks are copied
byte-for-byte; nothing inside a block is edited. The URL, UTC fetch time, HTTP status, the
full file size and the list of registry stations not found are appended to the folder README.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from edgefront_core.http import get_with_retry, make_client
from edgefront_core.registry import load_registry
from edgefront_core.timeutil import utcnow

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packages" / "core" / "tests" / "fixtures" / "nomads_text"
BASE = "https://nomads.ncep.noaa.gov/pub/data/nccf/com"


def url_for(product: str, cycle: str) -> str:
    day, hh = cycle[:8], cycle[8:10]
    if product == "nbh":
        return f"{BASE}/blend/prod/blend.{day}/{hh}/text/blend_nbhtx.t{hh}z"
    if product == "nbs":
        return f"{BASE}/blend/prod/blend.{day}/{hh}/text/blend_nbstx.t{hh}z"
    if product == "mav":
        return f"{BASE}/gfs_mos/prod/gfs_mos.{day}/mdl_gfsmav.t{hh}z"
    if product == "lav":  # full 1-25 h LAMP is the HH30 issuance (HH00/15/45 are CIG/VIS only)
        mm = cycle[10:12] or "30"
        return f"{BASE}/lmp/prod/lmp.{day}/lmp.t{hh}{mm}z.lavtxt.ascii"
    if product == "lavx":  # extended LAMP, hours 26-38 (HH30 issuances)
        mm = cycle[10:12] or "30"
        return f"{BASE}/lmp/prod/lmp.{day}/lmp.t{hh}{mm}z.lavtxt_ext.ascii"
    raise SystemExit(f"unknown product {product}")


HEADER = re.compile(r"^ ?([A-Z0-9]{3,5}) +(?:NBM|GFS)\b")


def split_blocks(text: str) -> dict[str, str]:
    """Station id -> block text (header line up to, not including, the next header)."""
    lines = text.splitlines(keepends=True)
    starts = [(i, m.group(1)) for i, ln in enumerate(lines) if (m := HEADER.match(ln))]
    blocks: dict[str, str] = {}
    for k, (i, sid) in enumerate(starts):
        j = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        blocks.setdefault(sid, "".join(lines[i:j]))
    return blocks


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("product", choices=["nbh", "nbs", "mav", "lav", "lavx"])
    p.add_argument("cycles", nargs="+", help="YYYYMMDDHH (lav: YYYYMMDDHHMM, default HH30)")
    p.add_argument("--extra", nargs="*", default=[])
    a = p.parse_args()
    ids = [s.id for s in load_registry()] + a.extra
    OUT.mkdir(parents=True, exist_ok=True)
    readme = OUT / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Fixtures: nomads_text\n\n"
            "Real NOMADS text bulletins. Each file keeps only the blocks for the registry "
            "stations (copied verbatim, in bulletin order); every other station block was "
            "dropped to keep the fixtures small. Requests sent with the EdgeFront User-Agent "
            "(CONTEXT.md §4).\n\n"
            "| File | URL | Fetched (UTC) | HTTP | Full size | Stations kept | Not in bulletin |\n"
            "|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
            newline="\n",
        )
    with make_client(timeout=120) as client:
        for cycle in a.cycles:
            url = url_for(a.product, cycle)
            fetched = utcnow()
            resp = get_with_retry(client, url)
            resp.raise_for_status()
            text = resp.content.decode("ascii")
            blocks = split_blocks(text)
            kept = [i for i in ids if i in blocks]
            missing = [i for i in ids if i not in blocks]
            name = f"{a.product}_{cycle}.txt"
            # keep bulletin order
            order = [sid for sid in blocks if sid in set(kept)]
            (OUT / name).write_text("".join(blocks[s] for s in order), encoding="ascii", newline="")
            with readme.open("a", encoding="utf-8", newline="\n") as f:
                f.write(
                    f"| `{name}` | {url} | {fetched.strftime('%Y-%m-%dT%H:%M:%SZ')} "
                    f"| {resp.status_code} | {len(resp.content):,} B, {len(blocks)} blocks "
                    f"| {len(kept)} | {', '.join(missing) or '—'} |\n"
                )
            print(name, len(resp.content), len(blocks), "kept", len(kept), "missing", missing)


if __name__ == "__main__":
    main()
