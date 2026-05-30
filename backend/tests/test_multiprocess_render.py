"""Parallel-render correctness tests for :meth:`BitmapConverter.render_from_segmentation`.

The contract is *byte-identical* output regardless of ``n_workers`` —
the layer-order loop builds jobs in a deterministic order and
``executor.map`` preserves it. Any future change that breaks
determinism (random ordering, set iteration, dict iteration across
workers) should fail this test.
"""

from __future__ import annotations

import multiprocessing
import sys

import numpy as np
import pytest

from pen_plotter.converters.bitmap import (
    BitmapConverter,
    BitmapOptions,
    SegmentationResult,
)


def _build_synthetic_segmentation(n_layers: int = 4, size: int = 60) -> SegmentationResult:
    """Tile ``n_layers`` distinct cluster IDs across a small canvas."""
    labels = np.zeros((size, size), dtype=np.intp)
    cell = size // n_layers
    palette_rows = []
    for i in range(n_layers):
        labels[:, i * cell : (i + 1) * cell] = i
        # Pick distinct dark colours so drop_background lets every layer through.
        palette_rows.append([(40 + i * 30) % 200, (80 + i * 20) % 200, (120 + i * 10) % 200])
    palette = np.array(palette_rows, dtype=np.uint8)
    return SegmentationResult(labels=labels, palette=palette, width=size, height=size)


def _forkserver_available() -> bool:
    """``forkserver`` is POSIX-only; Windows defaults to spawn."""
    if sys.platform == "win32":
        return False
    return "forkserver" in multiprocessing.get_all_start_methods()


@pytest.mark.skipif(not _forkserver_available(), reason="forkserver start method unavailable")
def test_parallel_output_matches_serial() -> None:
    seg = _build_synthetic_segmentation(n_layers=4)
    opts = BitmapOptions(algorithm="hilbert", num_colors=4, drop_background=False)

    serial_svg, serial_warnings = BitmapConverter.render_from_segmentation(seg, opts, n_workers=1)
    parallel_svg, parallel_warnings = BitmapConverter.render_from_segmentation(
        seg, opts, n_workers=2
    )
    # No warnings about pool failure should surface — that would mean we
    # silently took the serial fallback and the comparison is trivially true.
    assert not any("Parallel render disabled" in w for w in parallel_warnings)
    assert serial_svg == parallel_svg
    assert serial_warnings == parallel_warnings


@pytest.mark.skipif(not _forkserver_available(), reason="forkserver start method unavailable")
def test_parallel_handles_eulerian_hatch_layers() -> None:
    """All registered algorithms remain picklable from worker processes."""
    seg = _build_synthetic_segmentation(n_layers=3)
    opts = BitmapOptions(algorithm="eulerian_hatch", num_colors=3, drop_background=False)
    svg, _ = BitmapConverter.render_from_segmentation(seg, opts, n_workers=2)
    assert svg.count("<polyline") >= 1


def test_n_workers_one_uses_inline_render() -> None:
    """``n_workers=1`` (default) must never spawn workers — guards Pi 4 sanity."""
    seg = _build_synthetic_segmentation(n_layers=2)
    opts = BitmapOptions(algorithm="hilbert", num_colors=2, drop_background=False)
    svg, warnings = BitmapConverter.render_from_segmentation(seg, opts, n_workers=1)
    assert svg.count("<g ") >= 2
    assert warnings == []
