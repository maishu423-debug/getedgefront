"""Shared upstream HTTP client: NWS User-Agent, timeouts, retry/backoff on 5xx/429/network errors.

Only the worker and admin CLIs (seed/enrich/fixture capture) use this. API request paths never do.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Mapping

import httpx

from edgefront_core.settings import get_settings

log = logging.getLogger(__name__)

RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class UpstreamError(RuntimeError):
    pass


def make_client(timeout: float = 20.0) -> httpx.Client:
    settings = get_settings()
    if not settings.contact_email:
        raise UpstreamError("CONTACT_EMAIL is not set; NWS requires a contact in the User-Agent")
    return httpx.Client(
        headers={"User-Agent": settings.user_agent},
        timeout=timeout,
        follow_redirects=True,
    )


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    value = resp.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: Mapping[str, str] | None = None,
    headers: Mapping[str, str] | None = None,
    attempts: int = 4,
    base_delay: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """GET with exponential backoff + jitter. Returns the final response (2xx or a non-retryable
    4xx such as 404); raises UpstreamError when retries are exhausted."""
    last: str = ""
    for attempt in range(1, attempts + 1):
        try:
            resp = client.get(url, params=params, headers=headers)
        except httpx.TransportError as exc:
            last = f"{type(exc).__name__}: {exc}"
        else:
            if resp.status_code not in RETRY_STATUS:
                return resp
            last = f"HTTP {resp.status_code}"
            wait = _retry_after_seconds(resp)
            if wait is not None and attempt < attempts:
                sleep(min(wait, 60.0))
                continue
        if attempt < attempts:
            delay = base_delay * 2 ** (attempt - 1)
            delay += random.uniform(0, delay / 2)  # noqa: S311 - jitter, not crypto
            log.warning("upstream retry", extra={"url": url, "attempt": attempt, "error": last})
            sleep(delay)
    raise UpstreamError(f"GET {url} failed after {attempts} attempts: {last}")
