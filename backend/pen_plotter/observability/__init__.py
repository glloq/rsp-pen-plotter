"""Observability primitives — structured logging, correlation IDs, tracing.

This package provides the building blocks called out by the v0.2 roadmap
phase A: JSON-formatted logs, request/job correlation propagated via
contextvars, and (later) OpenTelemetry spans on top of the same context.

Import surface kept minimal: the public functions are
:func:`configure_logging`, :func:`bind_context`, :func:`get_context`, and
the middleware :class:`RequestContextMiddleware`.
"""

from __future__ import annotations

from pen_plotter.observability.context import (
    CORRELATION_FIELDS,
    bind_context,
    clear_context,
    get_context,
)
from pen_plotter.observability.logging_config import configure_logging
from pen_plotter.observability.middleware import RequestContextMiddleware
from pen_plotter.observability.tracing import (
    configure_tracing,
    is_tracing_enabled,
    traced_span,
)

__all__ = [
    "CORRELATION_FIELDS",
    "RequestContextMiddleware",
    "bind_context",
    "clear_context",
    "configure_logging",
    "configure_tracing",
    "get_context",
    "is_tracing_enabled",
    "traced_span",
]
