"""OpenTelemetry tracing configuration and helpers.

Roadmap step **A.2**. Tracing is opt-in: nothing is exported (and no
span processor is registered) unless ``OMNIPLOT_OTEL_ENABLED=1``. When
enabled, traces use 100 % sampling — fine for an appliance with low
traffic; multi-machine deployments will switch to tail-sampling later
(see roadmap D.6).

The :func:`traced_span` helper is the call-site API: it creates a span
with the given name, copies the currently bound correlation fields onto
it as attributes (so traces stay correlated with the JSON logs from
A.1), and returns a context manager. When tracing is disabled the
helper is a true no-op — no SDK calls, no allocations beyond the
nullcontext.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.sampling import ALWAYS_ON

from pen_plotter.observability.context import get_context

_log = logging.getLogger(__name__)

_TRACER_NAME = "pen_plotter"
_configured = False


def _truthy(raw: str | None) -> bool:
    if not raw:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def is_tracing_enabled() -> bool:
    """Return ``True`` when tracing was configured during startup."""
    return _configured


def configure_tracing(app: Any | None = None) -> None:
    """Install the OTel tracer provider when ``OMNIPLOT_OTEL_ENABLED`` is set.

    The exporter is chosen by ``OMNIPLOT_OTEL_EXPORTER``:

    - ``otlp`` (default) — POST spans to ``OMNIPLOT_OTLP_ENDPOINT``
      (default ``http://localhost:4318/v1/traces``).
    - ``console`` — pretty-print spans to stderr; useful for local dev.

    The service name on the OTel resource is taken from
    ``OMNIPLOT_SERVICE_NAME`` (default ``omniplot-backend``).

    When ``app`` is provided, FastAPI auto-instrumentation is installed
    on it so every route receives a server span automatically.
    """
    global _configured
    if _configured:
        return
    if not _truthy(os.environ.get("OMNIPLOT_OTEL_ENABLED")):
        return

    service_name = os.environ.get("OMNIPLOT_SERVICE_NAME", "omniplot-backend")
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource, sampler=ALWAYS_ON)

    exporter_kind = os.environ.get("OMNIPLOT_OTEL_EXPORTER", "otlp").strip().lower()
    if exporter_kind == "console":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    else:
        endpoint = os.environ.get(
            "OMNIPLOT_OTLP_ENDPOINT", "http://localhost:4318/v1/traces"
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )

    trace.set_tracer_provider(provider)
    if app is not None:
        FastAPIInstrumentor.instrument_app(app)

    _configured = True
    _log.info(
        "otel_configured",
        extra={"exporter": exporter_kind, "service_name": service_name},
    )


@contextmanager
def traced_span(name: str, **attributes: Any) -> Iterator[Any]:
    """Open a span named ``name`` with the current correlation context.

    Acts as a no-op context manager when tracing is disabled, so call
    sites can wrap any block unconditionally without paying for SDK
    plumbing on the appliance default configuration.
    """
    if not _configured:
        with nullcontext() as ctx:
            yield ctx
        return

    tracer = trace.get_tracer(_TRACER_NAME)
    span_attrs: dict[str, Any] = dict(get_context())
    for key, value in attributes.items():
        if value is None:
            continue
        span_attrs[key] = value
    with tracer.start_as_current_span(name, attributes=span_attrs) as span:
        yield span


def _reset_for_tests() -> None:
    """Test helper: clear the module-level configured flag."""
    global _configured
    _configured = False
