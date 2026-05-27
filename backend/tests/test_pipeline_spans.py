"""Verify B.5 sub-step spans are emitted on the bitmap pipeline.

The ``memory_exporter`` fixture is shared via ``tests/conftest.py``.
"""

from __future__ import annotations

import io

import numpy as np
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from PIL import Image

from pen_plotter.converters.pipeline import convert_file


def _png_bytes() -> bytes:
    arr = np.full((48, 48, 3), 255, np.uint8)
    arr[10:30, 10:30] = (220, 20, 20)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def test_bitmap_pipeline_emits_sub_step_spans(
    memory_exporter: InMemorySpanExporter,
) -> None:
    convert_file(
        _png_bytes(),
        "fixture.png",
        "image/png",
        options={"algorithm": "halftone", "num_colors": 2},
    )
    names = {s.name for s in memory_exporter.get_finished_spans()}
    # Top-level + sub-step spans expected (B.5).
    assert "pipeline.convert_file" in names
    assert "pipeline.segment_and_render" in names
    assert "pipeline.bitmap.load" in names
    assert "pipeline.bitmap.preprocess" in names
    assert "pipeline.bitmap.fit_within" in names
    assert "pipeline.bitmap.segment" in names
    assert "pipeline.bitmap.compose_svg" in names


def test_segment_span_carries_method_attribute(
    memory_exporter: InMemorySpanExporter,
) -> None:
    convert_file(
        _png_bytes(),
        "fixture.png",
        "image/png",
        options={"algorithm": "halftone", "num_colors": 2},
    )
    seg_spans = [
        s for s in memory_exporter.get_finished_spans() if s.name == "pipeline.bitmap.segment"
    ]
    assert seg_spans, "expected at least one pipeline.bitmap.segment span"
    attrs = dict(seg_spans[0].attributes or {})
    assert attrs.get("num_colors") == 2
    assert "method" in attrs


def test_convert_file_span_carries_size_and_mime(
    memory_exporter: InMemorySpanExporter,
) -> None:
    data = _png_bytes()
    convert_file(
        data, "fixture.png", "image/png", options={"algorithm": "halftone", "num_colors": 2}
    )
    spans = [
        s for s in memory_exporter.get_finished_spans() if s.name == "pipeline.convert_file"
    ]
    attrs = dict(spans[0].attributes or {})
    assert attrs["mime"] == "image/png"
    assert attrs["size_bytes"] == len(data)
