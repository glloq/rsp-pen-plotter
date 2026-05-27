r"""Measure end-to-end pipeline latency on synthetic fixtures.

Roadmap step **A.2 — perf baseline**. Run before any structural refactor
of the conversion pipeline so future phases can quote a delta against
this snapshot.

Usage::

    OMNIPLOT_DB=/tmp/perf.db OMNIPLOT_PROFILES_DIR=/tmp/perf-profiles \
        python scripts/perf_baseline.py --runs 7

Outputs a markdown table with p50/p95/p99 per phase per fixture. The
caller is expected to redirect stdout into ``docs/perf-baseline.md`` (or
a section thereof) when capturing a reference baseline.

The fixtures are deterministic and dependency-free so the baseline is
reproducible: a small two-tone PNG and a hand-written SVG. Real-world
fixtures (large photos, complex SVGs, multi-page PDFs) will be added
once the resolver/IR work in phase B requires calibration data.
"""

from __future__ import annotations

import argparse
import io
import os
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# Isolate runtime side-effects before importing the package (mirrors conftest).
os.environ.setdefault("OMNIPLOT_DB", str(Path(tempfile.gettempdir()) / "omniplot_perf.db"))
os.environ.setdefault(
    "OMNIPLOT_PROFILES_DIR", str(Path(tempfile.gettempdir()) / "omniplot_perf_profiles")
)


def _make_bitmap_fixture() -> bytes:
    import numpy as np
    from PIL import Image

    arr = np.full((128, 128, 3), 255, np.uint8)
    arr[20:60, 20:60] = (220, 20, 20)
    arr[60:108, 60:108] = (20, 80, 200)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def _make_svg_fixture() -> bytes:
    return (
        b'<?xml version="1.0"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">\n'
        b'  <g inkscape:label="black" '
        b'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">\n'
        b'    <path d="M10,10 L90,10 L90,90 L10,90 Z" stroke="black" fill="none"/>\n'
        b'    <path d="M30,30 L70,30 L70,70 L30,70 Z" stroke="black" fill="none"/>\n'
        b"  </g>\n"
        b"</svg>\n"
    )


@dataclass
class PhaseSamples:
    """Wall-clock samples (ms) for one pipeline phase across N runs."""

    name: str
    samples: list[float] = field(default_factory=list)

    def add(self, ms: float) -> None:
        """Append a sample."""
        self.samples.append(ms)

    def percentile(self, p: float) -> float:
        """Return the ``p``-th percentile (linear nearest-rank)."""
        if not self.samples:
            return 0.0
        ordered = sorted(self.samples)
        k = max(0, min(len(ordered) - 1, int(round((p / 100) * (len(ordered) - 1)))))
        return ordered[k]

    def p50(self) -> float:
        """Median."""
        return self.percentile(50)

    def p95(self) -> float:
        """95th percentile."""
        return self.percentile(95)

    def p99(self) -> float:
        """99th percentile."""
        return self.percentile(99)

    def mean(self) -> float:
        """Arithmetic mean."""
        return statistics.fmean(self.samples) if self.samples else 0.0


def _time_ms(fn: Callable[[], object]) -> tuple[float, object]:
    start = time.perf_counter()
    result = fn()
    return (time.perf_counter() - start) * 1000.0, result


def _run_bitmap(data: bytes) -> dict[str, float]:
    from pen_plotter.converters.pipeline import convert_file
    from pen_plotter.core.gcode import generate_gcode
    from pen_plotter.core.toolpath import optimize_svg
    from pen_plotter.models import MachineProfile
    from pen_plotter.profiles import load_profiles

    profile: MachineProfile = next(iter(load_profiles()))

    timings: dict[str, float] = {}
    t_convert, converted = _time_ms(
        lambda: convert_file(data, "fixture.png", "image/png",
                             options={"algorithm": "halftone", "num_colors": 2})
    )
    timings["convert"] = t_convert
    t_opt, optimized = _time_ms(lambda: optimize_svg(converted.svg))  # type: ignore[union-attr]
    timings["optimize"] = t_opt
    t_gcode, _ = _time_ms(lambda: generate_gcode(optimized.svg, profile))  # type: ignore[union-attr]
    timings["gcode"] = t_gcode
    return timings


def _run_svg(data: bytes) -> dict[str, float]:
    from pen_plotter.converters.pipeline import convert_file
    from pen_plotter.core.gcode import generate_gcode
    from pen_plotter.core.toolpath import optimize_svg
    from pen_plotter.models import MachineProfile
    from pen_plotter.profiles import load_profiles

    profile: MachineProfile = next(iter(load_profiles()))

    timings: dict[str, float] = {}
    t_convert, converted = _time_ms(
        lambda: convert_file(data, "fixture.svg", "image/svg+xml")
    )
    timings["convert"] = t_convert
    t_opt, optimized = _time_ms(lambda: optimize_svg(converted.svg))  # type: ignore[union-attr]
    timings["optimize"] = t_opt
    t_gcode, _ = _time_ms(lambda: generate_gcode(optimized.svg, profile))  # type: ignore[union-attr]
    timings["gcode"] = t_gcode
    return timings


_FIXTURES: dict[str, tuple[bytes, Callable[[bytes], dict[str, float]]]] = {
    "bitmap_photo (synthetic 128x128 PNG)": (_make_bitmap_fixture(), _run_bitmap),
    "vector_svg (synthetic 100x100)": (_make_svg_fixture(), _run_svg),
}


def _warmup() -> None:
    from pen_plotter.converters.defaults import register_default_converters
    from pen_plotter.converters.registry import registry
    from pen_plotter.persistence import init_db

    register_default_converters(registry)
    init_db()


def main() -> int:
    """CLI entry point: run fixtures, print markdown table, return 0."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs", type=int, default=5, help="Samples per fixture (default 5)"
    )
    parser.add_argument(
        "--warmup", type=int, default=1, help="Untimed warmup iterations (default 1)"
    )
    args = parser.parse_args()

    _warmup()

    print("# Perf baseline")
    print()
    print(f"- runs per fixture: **{args.runs}**")
    print(f"- warmup iterations: **{args.warmup}**")
    print()

    for fixture_name, (data, runner) in _FIXTURES.items():
        for _ in range(args.warmup):
            runner(data)
        phases: dict[str, PhaseSamples] = {}
        for _ in range(args.runs):
            timings = runner(data)
            for phase, ms in timings.items():
                phases.setdefault(phase, PhaseSamples(phase)).add(ms)

        print(f"## {fixture_name}")
        print()
        print("| phase    | mean (ms) | p50 (ms) | p95 (ms) | p99 (ms) |")
        print("|----------|-----------|----------|----------|----------|")
        for phase in ("convert", "optimize", "gcode"):
            s = phases.get(phase)
            if s is None:
                continue
            print(
                f"| {phase:<8} | {s.mean():>9.2f} | {s.p50():>8.2f} "
                f"| {s.p95():>8.2f} | {s.p99():>8.2f} |"
            )
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
