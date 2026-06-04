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


# Drop buckets idle longer than this. A bucket idle past its full-refill
# window is indistinguishable from a fresh one: tokens would have refilled
# to capacity. Dropping it reclaims the dict entry on a long-running
# appliance where transient clients (port scans, CI runners, …) would
# otherwise accumulate forever.
_BUCKET_TTL_SEC = 600.0
# Run the sweep at most every ``_SWEEP_INTERVAL_SEC`` seconds — cheap so
# the steady-state ``allow`` path stays a single dict lookup.
_SWEEP_INTERVAL_SEC = 60.0


class RateLimiter:
    """Token-bucket limiter keyed by client IP.

    ``capacity`` is the bucket size (burst), ``refill_per_sec`` is the
    steady-state rate. A request consumes one token; when the bucket is
    empty the request is rejected with 429.

    Buckets idle longer than ``_BUCKET_TTL_SEC`` are swept on the next
    ``allow`` call so the dict can't grow without bound on a long-running
    appliance (transient client IPs).
    """

    def __init__(self, *, capacity: int, refill_per_sec: float) -> None:
        """Store the bucket size and refill rate; buckets are created lazily."""
        self.capacity = float(capacity)
        self.refill_per_sec = refill_per_sec
        self._buckets: dict[str, _Bucket] = {}
        self._buckets_lock = Lock()
        self._last_sweep_at = time.monotonic()

    def _maybe_sweep(self, now: float) -> None:
        """Drop buckets idle longer than the TTL. Caller must hold the dict lock."""
        if now - self._last_sweep_at < _SWEEP_INTERVAL_SEC:
            return
        self._last_sweep_at = now
        cutoff = now - _BUCKET_TTL_SEC
        stale = [key for key, bucket in self._buckets.items() if bucket.updated_at < cutoff]
        for key in stale:
            del self._buckets[key]

    def allow(self, key: str) -> bool:
        """Try to consume one token for ``key``. Return ``True`` if allowed."""
        now = time.monotonic()
        with self._buckets_lock:
            self._maybe_sweep(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self.capacity, updated_at=now)
                self._buckets[key] = bucket
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
