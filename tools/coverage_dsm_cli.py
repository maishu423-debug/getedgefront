"""Coverage check: which of our stations have NWS DSM and CLI products, and where they can be seen.

    uv run python tools/coverage_dsm_cli.py [--out report.md]

DISCOVERY ONLY. Iowa Environmental Mesonet (IEM) is used here only to check whether NWS issues a
product; it is NOT a production source (its terms have not been reviewed, owner decision Q14).
Nothing in services/ or packages/ imports this file.

- api.weather.gov: /products/types/{DSM|CLI}/locations/{LOC} (NWS User-Agent with contact email)
- IEM: /api/1/nws/afos/list.json?pil=…&date=… (generic User-Agent, throttled: IEM returns 429
  when requests come too fast) and /cgi-bin/afos/retrieve.py as a fallback for older products.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from edgefront_core.http import get_with_retry, make_client
from edgefront_core.registry import load_registry

NWS = "https://api.weather.gov"
IEM = "https://mesonet.agron.iastate.edu"
IEM_UA = {"User-Agent": "EdgeFront/1.0 (getedgefront.com)"}  # no personal contact to 3rd parties
IEM_PAUSE = 3.0
LOOKBACK_DAYS = 3


@dataclass
class Seen:
    latest: datetime | None = None
    detail: str = ""

    def cell(self) -> str:
        if self.latest is None:
            return self.detail or "none"
        return f"{self.latest:%Y-%m-%d %H:%MZ}" + (f" ({self.detail})" if self.detail else "")


def nws_latest(client: httpx.Client, product: str, loc: str) -> Seen:
    r = get_with_retry(
        client,
        f"{NWS}/products/types/{product}/locations/{loc}",
        headers={"Accept": "application/ld+json"},
    )
    if r.status_code != 200:
        return Seen(None, f"HTTP {r.status_code}")
    graph = r.json().get("@graph") or []
    if not graph:
        return Seen(None, "none")
    g = graph[0]
    return Seen(datetime.fromisoformat(g["issuanceTime"]), g.get("issuingOffice", ""))


def _iem_get(client: httpx.Client, path: str, params: dict[str, str]) -> httpx.Response:
    for attempt in range(4):
        time.sleep(IEM_PAUSE * (attempt + 1))
        r = client.get(f"{IEM}{path}", params=params)
        if r.status_code != 429:
            return r
    return r


def iem_latest(client: httpx.Client, pil: str, now: datetime) -> Seen:
    for back in range(LOOKBACK_DAYS):
        day = (now - timedelta(days=back)).strftime("%Y-%m-%d")
        r = _iem_get(client, "/api/1/nws/afos/list.json", {"pil": pil, "date": day})
        if r.status_code != 200:
            return Seen(None, f"HTTP {r.status_code}")
        rows: list[dict[str, Any]] = r.json().get("data") or []
        if rows:
            best = max(rows, key=lambda x: x["entered"])
            wmo = best["product_id"].split("-")[2] if best["product_id"].count("-") >= 3 else ""
            return Seen(
                datetime.fromisoformat(best["entered"].replace("Z", "+00:00")),
                f"{best['cccc']} {wmo}".strip(),
            )
    r = _iem_get(client, "/cgi-bin/afos/retrieve.py", {"pil": pil, "limit": "1", "fmt": "text"})
    if r.status_code == 200 and r.text.strip():
        return Seen(None, f"older only (none in last {LOOKBACK_DAYS} d)")
    return Seen(None, "none")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    now = datetime.now(UTC)
    stations = load_registry()
    lines = [
        f"Coverage check run {now:%Y-%m-%d %H:%MZ}. IEM = discovery only.",
        "",
        "| Station | DSM PIL | DSM via api.weather.gov | DSM via IEM | CLI PIL | CLI via api.weather.gov | CLI via IEM |",  # noqa: E501
        "|---|---|---|---|---|---|---|",
    ]
    with make_client() as nws, httpx.Client(headers=IEM_UA, timeout=30) as iem:
        for st in stations:
            loc = st.id[1:]
            cells = [st.id]
            for product in ("DSM", "CLI"):
                pil = f"{product}{loc}"
                n = nws_latest(nws, product, loc)
                time.sleep(0.3)
                i = iem_latest(iem, pil, now)
                cells += [pil, n.cell(), i.cell()]
            row = "| " + " | ".join(cells) + " |"
            lines.append(row)
            sys.stdout.write(row + "\n")
            sys.stdout.flush()
    text = "\n".join(lines) + "\n"
    if a.out:
        a.out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
