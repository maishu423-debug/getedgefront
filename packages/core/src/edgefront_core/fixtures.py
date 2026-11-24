"""Capture a real upstream response as a test fixture (parsers are built from real files).

    python -m edgefront_core.fixtures <source> <filename> <url> [--accept MIME]

Saves to packages/core/tests/fixtures/<source>/<filename> and appends the exact URL and UTC
fetch time to that folder's README.md. The User-Agent (which contains the contact email) is
never written to disk.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

from edgefront_core.http import get_with_retry, make_client
from edgefront_core.timeutil import utcnow

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


THIRD_PARTY_UA = {"User-Agent": "EdgeFront/1.0 (getedgefront.com)"}  # no personal contact


def capture(
    source: str,
    filename: str,
    url: str,
    accept: str | None = None,
    *,
    third_party: bool = False,
) -> Path:
    """`third_party=True` (e.g. IEM): generic User-Agent without the NWS contact email."""
    folder = FIXTURES / source
    folder.mkdir(parents=True, exist_ok=True)
    client_cm = (
        httpx.Client(headers=THIRD_PARTY_UA, timeout=30, follow_redirects=True)
        if third_party
        else make_client()
    )
    with client_cm as client:
        fetched_at = utcnow()
        resp = get_with_retry(client, url, headers={"Accept": accept} if accept else None)
    resp.raise_for_status()
    out = folder / filename
    out.write_bytes(resp.content)

    readme = folder / "README.md"
    if not readme.exists():
        readme.write_text(
            f"# Fixtures: {source}\n\nReal upstream responses, saved verbatim. "
            + (
                "Requests sent with a generic EdgeFront User-Agent (third-party host, no contact "
                "email).\n\n"
                if third_party
                else "Requests sent with the NWS User-Agent from CONTEXT.md §4.\n\n"
            )
            + "| File | URL | Fetched (UTC) | HTTP |\n|---|---|---|---|\n",
            encoding="utf-8",
            newline="\n",
        )
    with readme.open("a", encoding="utf-8", newline="\n") as f:
        f.write(
            f"| `{filename}` | {url} | {fetched_at.strftime('%Y-%m-%dT%H:%M:%SZ')} "
            f"| {resp.status_code} |\n"
        )
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source")
    p.add_argument("filename")
    p.add_argument("url")
    p.add_argument("--accept")
    a = p.parse_args(argv)
    out = capture(a.source, a.filename, a.url, a.accept)
    sys.stdout.write(f"saved {out} ({out.stat().st_size} bytes)\n")


if __name__ == "__main__":
    main()
