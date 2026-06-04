"""Lightweight in-process rate limiting middleware.

Single-appliance design: a token-bucket per client IP, kept in memory,
no external dependency (Redis / slowapi) so the Pi appliance keeps
working offline. Tuned for v0.2: defaults sized for one operator
clicking around the SPA, not a public-facing service.

Operators tune limits via env vars:

* ``OMNIPLOT_RATE_LIMIT_RPM`` — requests per minute (default 600 → 10/s).
* ``OMNIPLOT_RATE_LIMIT_BURST`` — extra tokens for short bursts
  (default 60, so a quick wizard click-through doesn't trip).
* ``OMNIPLOT_RATE_LIMIT_ENABLED`` — set to ``0`` to disable (e.g. for
  load tests). Default ``1``.

Endpoints exempted from the limit: ``/health`` (so probes never get
429) and ``/static`` mounts (the SPA's own assets).
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from pen_plotter.errors import ApiErrorBody


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


_EXEMPT_PREFIXES = ("/health", "/static", "/assets")


@dataclass
class _Bucket:
    tokens: float
    updated_at: float
    lock: Lock = field(default_factory=Lock)


class RateLimiter:
    """Token-bucket limiter keyed by client IP.

    ``capacity`` is the bucket size (burst), ``refill_per_sec`` is the
    steady-state rate. A request consumes one token; when the bucket is
    empty the request is rejected with 429.
    """

    def __init__(self, *, capacity: int, refill_per_sec: float) -> None:
        """Store the bucket size and refill rate; buckets are created lazily."""
        self.capacity = float(capacity)
        self.refill_per_sec = refill_per_sec
        self._buckets: dict[str, _Bucket] = defaultdict(
            lambda: _Bucket(tokens=self.capacity, updated_at=time.monotonic())
        )
        self._buckets_lock = Lock()

    def allow(self, key: str) -> bool:
        """Try to consume one token for ``key``. Return ``True`` if allowed."""
        with self._buckets_lock:
            bucket = self._buckets[key]
        now = time.monotonic()
        with bucket.lock:
            elapsed = now - bucket.updated_at
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_per_sec)
            bucket.updated_at = now
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True
            return False


def _client_key(request: Request) -> str:
    """Resolve a stable identifier for the caller (IP for now)."""
    client = request.client
    if client is not None and client.host:
        return client.host
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or "anonymous"


def install_rate_limit(app: FastAPI) -> None:
    """Attach the rate-limit middleware unless disabled by env var."""
    if not _env_bool("OMNIPLOT_RATE_LIMIT_ENABLED", True):
        return

    rpm = _env_int("OMNIPLOT_RATE_LIMIT_RPM", 600)
    burst = _env_int("OMNIPLOT_RATE_LIMIT_BURST", 60)
    limiter = RateLimiter(capacity=burst, refill_per_sec=rpm / 60.0)

    @app.middleware("http")
    async def _rate_limit_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            return await call_next(request)
        key = _client_key(request)
        if not limiter.allow(key):
            body = ApiErrorBody(
                code="rate_limited",
                message="too many requests; slow down",
                details={"limit_rpm": rpm, "burst": burst},
                path=path,
            )
            return JSONResponse(status_code=429, content=body.model_dump())
        return await call_next(request)
