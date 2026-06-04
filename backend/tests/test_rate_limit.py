"""In-process rate limiter (P2).

The middleware is wired via env vars so these tests force tight limits,
build a fresh FastAPI app, and assert 429 once the bucket drains.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pen_plotter.rate_limit import RateLimiter, install_rate_limit


def test_token_bucket_allows_then_blocks() -> None:
    limiter = RateLimiter(capacity=2, refill_per_sec=0.0)
    assert limiter.allow("a") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
    # Other key has its own bucket.
    assert limiter.allow("b") is True


def test_token_bucket_refills_per_key() -> None:
    limiter = RateLimiter(capacity=1, refill_per_sec=1000.0)
    assert limiter.allow("k") is True
    # Drain.
    assert limiter.allow("k") is False
    # Wait long enough for the bucket to refill at least one token.
    # 50 ms is comfortably above the 1 ms refill window so CI runners
    # under load don't flake on the next allow().
    import time

    time.sleep(0.05)
    assert limiter.allow("k") is True


def test_idle_buckets_are_swept() -> None:
    """Dict can't grow without bound on a long-running appliance."""
    from pen_plotter import rate_limit as rate_limit_mod

    limiter = RateLimiter(capacity=10, refill_per_sec=1.0)
    # Seed three buckets.
    for key in ("a", "b", "c"):
        assert limiter.allow(key) is True
    assert len(limiter._buckets) == 3

    # Backdate the three buckets to look idle past the TTL, and the
    # sweep gate to look due. Sweep keys off ``now`` inside ``allow``
    # (real monotonic time) so we push the stale rows into the past,
    # not the new ones into the future.
    for bucket in limiter._buckets.values():
        bucket.updated_at -= rate_limit_mod._BUCKET_TTL_SEC + 10
    limiter._last_sweep_at -= rate_limit_mod._SWEEP_INTERVAL_SEC + 10

    # Touch a new bucket. The sweep must drop the three stale entries
    # but keep the fresh one.
    assert limiter.allow("d") is True
    assert set(limiter._buckets.keys()) == {"d"}


def test_anonymous_fallback_key() -> None:
    """No client IP and no X-Forwarded-For collapses everyone into one bucket."""
    from unittest.mock import Mock

    from pen_plotter.rate_limit import _client_key

    request = Mock()
    request.client = None
    request.headers = {"x-forwarded-for": ""}
    assert _client_key(request) == "anonymous"

    request.client = None
    request.headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}
    # The leftmost forwarded IP wins; intermediate proxies append on the right.
    assert _client_key(request) == "1.2.3.4"


def test_middleware_emits_429_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIPLOT_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("OMNIPLOT_RATE_LIMIT_RPM", "60")
    monkeypatch.setenv("OMNIPLOT_RATE_LIMIT_BURST", "2")
    app = FastAPI()
    install_rate_limit(app)

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"ok": "1"}

    client = TestClient(app)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    blocked = client.get("/ping")
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["code"] == "rate_limited"
    assert "limit_rpm" in body["details"]


def test_health_and_static_are_exempt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIPLOT_RATE_LIMIT_ENABLED", "1")
    monkeypatch.setenv("OMNIPLOT_RATE_LIMIT_RPM", "60")
    monkeypatch.setenv("OMNIPLOT_RATE_LIMIT_BURST", "1")
    app = FastAPI()
    install_rate_limit(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api")
    def api() -> dict[str, str]:
        return {"ok": "1"}

    client = TestClient(app)
    # Drain the bucket on a guarded endpoint.
    assert client.get("/api").status_code == 200
    assert client.get("/api").status_code == 429
    # /health stays open.
    for _ in range(5):
        assert client.get("/health").status_code == 200


def test_disable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIPLOT_RATE_LIMIT_ENABLED", "0")
    app = FastAPI()
    install_rate_limit(app)

    @app.get("/api")
    def api() -> dict[str, str]:
        return {"ok": "1"}

    client = TestClient(app)
    for _ in range(50):
        assert client.get("/api").status_code == 200
