import io
import os
import tempfile

# Isolate the job-history database and user profiles dir before pen_plotter imports.
os.environ.setdefault("OMNIPLOT_DB", os.path.join(tempfile.gettempdir(), "omniplot_test.db"))
os.environ.setdefault(
    "OMNIPLOT_PROFILES_DIR", os.path.join(tempfile.gettempdir(), "omniplot_test_profiles")
)
os.environ.setdefault(
    "OMNIPLOT_MACROS_FILE", os.path.join(tempfile.gettempdir(), "omniplot_test_macros.json")
)

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from opentelemetry import trace  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)
from PIL import Image  # noqa: E402

from pen_plotter.converters.defaults import register_default_converters  # noqa: E402
from pen_plotter.converters.registry import registry  # noqa: E402
from pen_plotter.persistence import init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _app_setup() -> None:
    """Prime the converter registry and database, mirroring the app lifespan."""
    register_default_converters(registry)
    init_db()


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the --update-goldens flag used by golden G-code tests."""
    parser.addoption(
        "--update-goldens",
        action="store_true",
        default=False,
        help="Rewrite golden G-code files instead of comparing against them.",
    )


@pytest.fixture
def update_goldens(request: pytest.FixtureRequest) -> bool:
    """True when the runner was invoked with --update-goldens."""
    return bool(request.config.getoption("--update-goldens"))


# Process-wide OTel TracerProvider for tests that want to assert on
# emitted spans. OTel refuses to override an already-installed provider,
# so multiple test files that need an in-memory exporter must share
# this one. The provider is created on first call; the exporter is
# cleared per test via the ``memory_exporter`` fixture below.
_OTEL_EXPORTER: InMemorySpanExporter | None = None


def _ensure_otel_provider() -> InMemorySpanExporter:
    global _OTEL_EXPORTER
    if _OTEL_EXPORTER is None:
        _OTEL_EXPORTER = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(_OTEL_EXPORTER))
        try:
            trace.set_tracer_provider(provider)
        except Exception:
            pass
    return _OTEL_EXPORTER


@pytest.fixture
def memory_exporter() -> InMemorySpanExporter:
    """Cleared in-memory OTel exporter; flips ``traced_span`` on for the test."""
    exporter = _ensure_otel_provider()
    exporter.clear()
    import pen_plotter.observability.tracing as tracing_mod

    tracing_mod._configured = True
    try:
        yield exporter
    finally:
        tracing_mod._configured = False
        exporter.clear()


@pytest.fixture
def two_color_png() -> bytes:
    """A 40x40 PNG: red square on a white background."""
    arr = np.full((40, 40, 3), 255, np.uint8)
    arr[10:30, 10:30] = (220, 20, 20)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()
