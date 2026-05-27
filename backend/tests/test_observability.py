"""Tests for the structured logging + correlation ID middleware (roadmap A.1)."""

from __future__ import annotations

import io
import json
import logging

import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.main import app
from pen_plotter.observability.context import bind_context, clear_context, get_context
from pen_plotter.observability.logging_config import JsonFormatter, configure_logging


def _capture(logger_name: str = "pen_plotter.test") -> tuple[logging.Logger, io.StringIO]:
    """Wire a fresh JSON handler on its own logger so tests don't fight stderr."""
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger, buf


def test_json_formatter_emits_required_fields() -> None:
    logger, buf = _capture()
    logger.info("hello", extra={"foo": "bar"})
    payload = json.loads(buf.getvalue().strip())
    assert payload["msg"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["foo"] == "bar"
    assert "ts" in payload
    assert "logger" in payload


def test_json_formatter_includes_correlation_context() -> None:
    logger, buf = _capture()
    tokens = bind_context(request_id="req-1", job_id="job-42", algorithm_id="stippling")
    try:
        logger.info("with-ctx")
    finally:
        clear_context(tokens)
    payload = json.loads(buf.getvalue().strip())
    assert payload["request_id"] == "req-1"
    assert payload["job_id"] == "job-42"
    assert payload["algorithm_id"] == "stippling"


def test_json_formatter_redacts_sensitive_keys() -> None:
    logger, buf = _capture()
    logger.info(
        "auth attempt",
        extra={"headers": {"Authorization": "Bearer s3cret", "X-Trace": "ok"}},
    )
    payload = json.loads(buf.getvalue().strip())
    assert payload["headers"]["Authorization"] == "***"
    assert payload["headers"]["X-Trace"] == "ok"


def test_json_formatter_serializes_exception() -> None:
    logger, buf = _capture()
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failed")
    payload = json.loads(buf.getvalue().strip())
    assert payload["level"] == "ERROR"
    assert "ValueError: boom" in payload["exc"]


def test_bind_context_rejects_unknown_field() -> None:
    with pytest.raises(KeyError):
        bind_context(not_a_field="x")


def test_get_context_returns_only_bound_fields() -> None:
    assert get_context() == {}
    tokens = bind_context(request_id="r")
    try:
        ctx = get_context()
    finally:
        clear_context(tokens)
    assert ctx == {"request_id": "r"}


def test_configure_logging_is_idempotent() -> None:
    configure_logging(force=True)
    handlers_before = list(logging.getLogger().handlers)
    configure_logging()
    handlers_after = list(logging.getLogger().handlers)
    assert len(handlers_before) == len(handlers_after)


@pytest.mark.asyncio
async def test_middleware_echoes_request_id_header() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": "trace-abc"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "trace-abc"


@pytest.mark.asyncio
async def test_middleware_generates_request_id_when_missing() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert len(response.headers["x-request-id"]) >= 16
