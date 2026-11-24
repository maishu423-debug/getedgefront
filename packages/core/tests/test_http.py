from __future__ import annotations

import httpx
import pytest

from edgefront_core.http import UpstreamError, get_with_retry, make_client


def _client(statuses: list[int]) -> tuple[httpx.Client, list[int]]:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        code = statuses[min(len(calls), len(statuses) - 1)]
        calls.append(code)
        return httpx.Response(code, json={})

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_retries_5xx_then_succeeds() -> None:
    c, calls = _client([503, 502, 200])
    r = get_with_retry(c, "https://x.test/", sleep=lambda _s: None)
    assert r.status_code == 200
    assert calls == [503, 502, 200]


def test_404_is_returned_not_retried() -> None:
    c, calls = _client([404])
    assert get_with_retry(c, "https://x.test/", sleep=lambda _s: None).status_code == 404
    assert calls == [404]


def test_gives_up_after_attempts() -> None:
    c, calls = _client([500])
    with pytest.raises(UpstreamError, match="HTTP 500"):
        get_with_retry(c, "https://x.test/", attempts=3, sleep=lambda _s: None)
    assert len(calls) == 3


def test_make_client_requires_contact_email(monkeypatch: pytest.MonkeyPatch) -> None:
    import edgefront_core.http as http_mod
    from edgefront_core.settings import Settings

    monkeypatch.setattr(http_mod, "get_settings", lambda: Settings(contact_email=""))
    with pytest.raises(UpstreamError, match="CONTACT_EMAIL"):
        make_client()
