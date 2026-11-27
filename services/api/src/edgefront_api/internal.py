"""Internal routes for the Next.js server only (v2 §V2.4, Phase 7 C).

Everything under `/api/v1/internal/` requires the header `X-Internal-Token` to equal the
`INTERNAL_API_TOKEN` setting (constant-time compare). Defence in depth: the API is already
reachable only on Railway's private network, and the browser never calls FastAPI. If the setting
is empty, every internal request is refused (fail closed). Public routes are unaffected.
Phase 9 adds the Premium data endpoints under this prefix.
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

INTERNAL_PREFIX = "/api/v1/internal"
HEADER = "X-Internal-Token"
log = logging.getLogger("edgefront.api.internal")

internal_router = APIRouter(prefix=INTERNAL_PREFIX)


@internal_router.get("/ping")
def ping() -> dict[str, bool]:
    """Lets the web server (and tests) prove the token is accepted."""
    return {"ok": True}


async def require_internal_token(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    path = request.url.path
    if path == INTERNAL_PREFIX or path.startswith(INTERNAL_PREFIX + "/"):
        expected: str = request.app.state.settings.internal_api_token
        given = request.headers.get(HEADER, "")
        if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
            log.warning(
                "internal route refused",
                extra={"path": path, "token_configured": bool(expected), "token_sent": bool(given)},
            )
            return JSONResponse({"detail": "forbidden"}, status_code=403)
    return await call_next(request)
