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
    import time

    time.sleep(0.01)
    assert limiter.allow("k") is True


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
