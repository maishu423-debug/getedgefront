"""Where the GRIB fields live and how to fetch only the bytes we need (CONTEXT §4.4).

- GFS 0.25°: NOAA open-data bucket on AWS (primary) or NOMADS (fallback), wgrib2 `.idx`
  inventories, one HTTP Range request per message.
- IFS and AIFS 0.25° (ECMWF open data, CC BY 4.0): JSON-lines `.index` files with
  `_offset`/`_length` per field. URL layout as built by the `ecmwf-opendata` package
  (verified 2026-11-25; 06Z/18Z runs use the `oper` stream too).

All requests go through EdgeFront's own HTTP client, so every upstream sees the EdgeFront
User-Agent with contact (owner A2). The Herbie / ecmwf-opendata download paths use the
default `python-requests` agent (and Herbie pings a third-party mirror), so they are not used
for transfers; see CONTEXT §4.4.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import httpx

from edgefront_core.http import UpstreamError, get_with_retry

GFS_AWS = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
GFS_NOMADS = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod"
ECMWF = "https://data.ecmwf.int/forecasts"


@dataclass(frozen=True)
class MessageRef:
    key: str  # our name: temp | dewpt | rh | u10 | v10 | cloud | lsm | orog
    url: str
    offset: int
    length: int | None  # None: to the end of the file (last message)


# ---------------------------------------------------------------- GFS


def gfs_url(base: str, cycle: datetime, fxx: int) -> str:
    d, hh = cycle.strftime("%Y%m%d"), cycle.strftime("%H")
    return f"{base}/gfs.{d}/{hh}/atmos/gfs.t{hh}z.pgrb2.0p25.f{fxx:03d}"


def gfs_patterns(fxx: int) -> dict[str, str]:
    """wgrib2 inventory fields per step (instantaneous TCDC, not the N-hour average)."""
    fc = "anl" if fxx == 0 else f"{fxx} hour fcst"
    pats = {
        "temp": f":TMP:2 m above ground:{fc}:",
        "dewpt": f":DPT:2 m above ground:{fc}:",
        "rh": f":RH:2 m above ground:{fc}:",
        "u10": f":UGRD:10 m above ground:{fc}:",
        "v10": f":VGRD:10 m above ground:{fc}:",
        "cloud": f":TCDC:entire atmosphere:{fc}:",
    }
    if fxx == 0:
        pats |= {"lsm": ":LAND:surface:anl:", "orog": ":HGT:surface:anl:"}
    return pats


_IDX = re.compile(r"^(\d+):(\d+):d=\d{10}(:.*)$")


def parse_wgrib_idx(text: str, url: str, patterns: dict[str, str]) -> dict[str, MessageRef]:
    rows = []
    for line in text.splitlines():
        m = _IDX.match(line.strip())
        if m:
            rows.append(
                (
                    int(m.group(1)),
                    int(m.group(2)),
                    m.group(3) if m.group(3).endswith(":") else m.group(3) + ":",
                )
            )
    out: dict[str, MessageRef] = {}
    for k, (_, off, desc) in enumerate(rows):
        nxt = rows[k + 1][1] if k + 1 < len(rows) else None
        for key, pat in patterns.items():
            if desc == pat and key not in out:
                out[key] = MessageRef(key, url, off, None if nxt is None else nxt - off)
    return out


# ---------------------------------------------------------------- ECMWF


ECMWF_PARAMS = {"2t": "temp", "2d": "dewpt", "10u": "u10", "10v": "v10", "tcc": "cloud"}
ECMWF_STATIC = {"lsm": "lsm", "z": "orog"}


def ecmwf_url(model: str, cycle: datetime, step: int) -> str:
    """`model` is the open-data name: ifs | aifs-single."""
    d, hh = cycle.strftime("%Y%m%d"), cycle.strftime("%H")
    return f"{ECMWF}/{d}/{hh}z/{model}/0p25/oper/{d}{hh}0000-{step}h-oper-fc.grib2"


def parse_ecmwf_index(text: str, url: str, with_static: bool) -> dict[str, MessageRef]:
    want = ECMWF_PARAMS | (ECMWF_STATIC if with_static else {})
    out: dict[str, MessageRef] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("levtype") not in ("sfc", None):
            continue
        key = want.get(row.get("param", ""))
        if key and key not in out:
            out[key] = MessageRef(key, url, int(row["_offset"]), int(row["_length"]))
    return out


# ---------------------------------------------------------------- transfer


class Fetcher:
    def __init__(
        self, client: httpx.Client, *, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self.client = client
        self.sleep = sleep
        self.bytes = 0
        self.requests = 0

    def text(self, url: str) -> str | None:
        """An index file, or None when it does not exist (yet)."""
        r = get_with_retry(self.client, url, sleep=self.sleep)
        self.requests += 1
        if r.status_code in (403, 404):
            return None
        r.raise_for_status()
        self.bytes += len(r.content)
        return r.text

    def message(self, ref: MessageRef) -> bytes:
        end = "" if ref.length is None else str(ref.offset + ref.length - 1)
        r = get_with_retry(
            self.client, ref.url, headers={"Range": f"bytes={ref.offset}-{end}"}, sleep=self.sleep
        )
        self.requests += 1
        if r.status_code != 206:
            raise UpstreamError(f"range request to {ref.url} answered HTTP {r.status_code}")
        if ref.length is not None and len(r.content) != ref.length:
            raise UpstreamError(f"{ref.url}: got {len(r.content)} bytes, wanted {ref.length}")
        if not r.content.startswith(b"GRIB"):
            raise UpstreamError(f"{ref.url}@{ref.offset}: not a GRIB message")
        self.bytes += len(r.content)
        return r.content
