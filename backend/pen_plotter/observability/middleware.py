"""ASGI middleware that binds the per-request correlation context.

Reads an inbound ``X-Request-ID`` header when present (so an upstream
proxy or test harness can correlate calls), otherwise mints a fresh
UUID4. The same value is echoed back on the response so the client can
quote it when reporting an issue.

A start/end log pair is emitted at INFO level with method, path,
status, and wall-clock duration — sufficient for a baseline access log
without pulling in another dependency.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from pen_plotter.observability.context import bind_context, clear_context

_log = logging.getLogger("pen_plotter.access")

_HEADER = "x-request-id"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind ``request_id`` for the lifetime of one HTTP request."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Mint or accept the request ID, bind context, log the call."""
        request_id = request.headers.get(_HEADER) or uuid.uuid4().hex
        tokens = bind_context(request_id=request_id)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers[_HEADER] = request_id
            return response
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            _log.info(
                "http_request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "elapsed_ms": round(elapsed_ms, 2),
                },
            )
            clear_context(tokens)
