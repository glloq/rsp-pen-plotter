"""Tests for the OTel tracing helpers (roadmap A.2).

The ``memory_exporter`` fixture comes from ``tests/conftest.py`` —
OTel refuses to override an already-installed TracerProvider, so the
process-wide one is shared across all test modules that need to
assert on emitted spans.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from pen_plotter.observability import bind_context, clear_context, traced_span
from pen_plotter.observability.tracing import (
    _reset_for_tests,
    configure_tracing,
    is_tracing_enabled,
)


def test_traced_span_is_noop_when_disabled() -> None:
    _reset_for_tests()
    assert not is_tracing_enabled()
    with traced_span("noop") as span:
        assert span is None


def test_traced_span_emits_span_with_correlation_attributes(
    memory_exporter: InMemorySpanExporter,
) -> None:
    tokens = bind_context(job_id="job-99", algorithm_id="stippling")
    try:
        with traced_span("phase.x", extra="ok"):
            pass
    finally:
        clear_context(tokens)
    spans = memory_exporter.get_finished_spans()
    assert len(spans) == 1
    attrs = dict(spans[0].attributes or {})
    assert attrs["job_id"] == "job-99"
    assert attrs["algorithm_id"] == "stippling"
    assert attrs["extra"] == "ok"
    assert spans[0].name == "phase.x"


def test_traced_span_skips_none_attributes(memory_exporter: InMemorySpanExporter) -> None:
    with traced_span("phase.y", kept="v", dropped=None):
        pass
    attrs = dict(memory_exporter.get_finished_spans()[0].attributes or {})
    assert attrs["kept"] == "v"
    assert "dropped" not in attrs


def test_configure_tracing_noop_when_env_var_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNIPLOT_OTEL_ENABLED", raising=False)
    _reset_for_tests()
    configure_tracing(None)
    assert not is_tracing_enabled()


def test_configure_tracing_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIPLOT_OTEL_ENABLED", "1")
    monkeypatch.setenv("OMNIPLOT_OTEL_EXPORTER", "console")
    _reset_for_tests()
    configure_tracing(None)
    assert is_tracing_enabled()
    configure_tracing(None)  # second call is a no-op
    assert is_tracing_enabled()
    _reset_for_tests()
