"""api.weather.gov text products: list a type/location, fetch only products we don't have.

Conditional requests: the list endpoint's `Last-Modified` is remembered per URL (in process) and
sent back as `If-Modified-Since`; a 304 means nothing new.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from edgefront_core.http import get_with_retry

NWS = "https://api.weather.gov"
LD = {"Accept": "application/ld+json"}


@dataclass(frozen=True)
class RawProduct:
    product_id: str
    issued_at: datetime
    issuer: str | None
    wmo_header: str | None
    text: str
    url: str


class NwsProductLister:
    def __init__(
        self,
        client: httpx.Client,
        *,
        sleep: Callable[[float], None] = time.sleep,
        pause_s: float = 0.25,
    ) -> None:
        self.client = client
        self.sleep = sleep
        self.pause_s = pause_s
        self._last_modified: dict[str, str] = {}

    def _get(self, url: str, headers: dict[str, str]) -> httpx.Response:
        self.sleep(self.pause_s)
        return get_with_retry(self.client, url, headers=headers, sleep=self.sleep)

    def new_products(
        self,
        product_type: str,
        location: str,
        known_ids: Iterable[str],
        *,
        since: datetime,
    ) -> list[RawProduct]:
        """Products of `product_type`/`location` issued after `since` that are not in known_ids."""
        url = f"{NWS}/products/types/{product_type}/locations/{location}"
        headers = dict(LD)
        if url in self._last_modified:
            headers["If-Modified-Since"] = self._last_modified[url]
        r = self._get(url, headers)
        if r.status_code == 304:
            return []
        r.raise_for_status()
        if lm := r.headers.get("Last-Modified"):
            self._last_modified[url] = lm
        known = set(known_ids)
        out: list[RawProduct] = []
        for item in r.json().get("@graph") or []:
            issued = datetime.fromisoformat(item["issuanceTime"])
            if issued < since or item["id"] in known:
                continue
            purl = f"{NWS}/products/{item['id']}"
            pr = self._get(purl, LD)
            pr.raise_for_status()
            doc = pr.json()
            text = doc.get("productText") or ""
            wmo = next(
                (ln.strip() for ln in text.splitlines()[:6] if ln.strip()[:4].isalpha()
                 and len(ln.split()) >= 3 and ln.split()[2].isdigit()),
                None,
            )  # fmt: skip
            out.append(
                RawProduct(
                    product_id=item["id"],
                    issued_at=issued,
                    issuer=item.get("issuingOffice"),
                    wmo_header=wmo,
                    text=text,
                    url=purl,
                )
            )
        return out


def lookback(now: datetime, days: int = 3) -> datetime:
    return now - timedelta(days=days)
