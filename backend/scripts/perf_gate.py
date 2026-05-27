"""Smoke perf gate (roadmap D.5).

Runs the deterministic synthetic fixtures from ``perf_baseline.py``
and fails the CI when the measured p95 for any phase regresses by
more than ``--allowed-regression-pct`` (default 50 %) over the
reference values committed in ``docs/perf-baseline.md`` (extracted
from a small constant table below for speed; updating the constants
is a deliberate ack of a perf change in the PR that pushes them).

Conservative defaults: the gate aims to catch *catastrophic* moves
(orders of magnitude) without flapping on noise. Tighten as the
phase D quick wins land.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("OMNIPLOT_DB", str(Path(tempfile.gettempdir()) / "omniplot_perfgate.db"))
os.environ.setdefault(
    "OMNIPLOT_PROFILES_DIR", str(Path(tempfile.gettempdir()) / "omniplot_perfgate_profiles")
)


# Reference p95 (ms) per fixture / phase, captured at the v0.2 entry
# point. CI fails when measured > REFERENCE * (1 + allowed_pct / 100).
REFERENCE_P95: dict[str, dict[str, float]] = {
    "bitmap_photo": {
        "convert": 600.0,
        "optimize": 130.0,
        "gcode": 200.0,
    },
    "vector_svg": {
        "convert": 5.0,
        "optimize": 10.0,
        "gcode": 5.0,
    },
}


@dataclass
class FixtureResult:
    """All phase samples for one fixture run."""

    name: str
    samples: dict[str, list[float]]


def _bitmap_bytes() -> bytes:
    import numpy as np
    from PIL import Image

    arr = np.full((128, 128, 3), 255, np.uint8)
    arr[20:60, 20:60] = (220, 20, 20)
    arr[60:108, 60:108] = (20, 80, 200)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def _svg_bytes() -> bytes:
    return (
        b'<?xml version="1.0"?>\n'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">\n'
        b'  <g inkscape:label="black" '
        b'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">\n'
        b'    <path d="M10,10 L90,10 L90,90 L10,90 Z" stroke="black" fill="none"/>\n'
        b"  </g>\n"
        b"</svg>\n"
    )


def _time(fn: Callable[[], object]) -> tuple[float, object]:
    start = time.perf_counter()
    out = fn()
    return (time.perf_counter() - start) * 1000.0, out


def _measure_bitmap(data: bytes, runs: int) -> dict[str, list[float]]:
    from pen_plotter.converters.pipeline import convert_file
    from pen_plotter.core.gcode import generate_gcode
    from pen_plotter.core.toolpath import optimize_svg
    from pen_plotter.profiles import load_profiles

    profile = next(iter(load_profiles()))
    samples: dict[str, list[float]] = {"convert": [], "optimize": [], "gcode": []}
    for _ in range(runs):
        t1, converted = _time(
            lambda: convert_file(
                data,
                "fixture.png",
                "image/png",
                options={"algorithm": "halftone", "num_colors": 2},
            )
        )
        samples["convert"].append(t1)
        cvt = converted  # bind loop var into the closures below
        t2, optimized = _time(lambda c=cvt: optimize_svg(c.svg))  # type: ignore[attr-defined]
        samples["optimize"].append(t2)
        opt = optimized
        t3, _ = _time(lambda o=opt: generate_gcode(o.svg, profile))  # type: ignore[attr-defined]
        samples["gcode"].append(t3)
    return samples


def _measure_vector(data: bytes, runs: int) -> dict[str, list[float]]:
    from pen_plotter.converters.pipeline import convert_file
    from pen_plotter.core.gcode import generate_gcode
    from pen_plotter.core.toolpath import optimize_svg
    from pen_plotter.profiles import load_profiles

    profile = next(iter(load_profiles()))
    samples: dict[str, list[float]] = {"convert": [], "optimize": [], "gcode": []}
    for _ in range(runs):
        t1, converted = _time(
            lambda: convert_file(data, "fixture.svg", "image/svg+xml")
        )
        samples["convert"].append(t1)
        cvt = converted  # bind loop var into the closures below
        t2, optimized = _time(lambda c=cvt: optimize_svg(c.svg))  # type: ignore[attr-defined]
        samples["optimize"].append(t2)
        opt = optimized
        t3, _ = _time(lambda o=opt: generate_gcode(o.svg, profile))  # type: ignore[attr-defined]
        samples["gcode"].append(t3)
    return samples


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def main() -> int:
    """CLI entry. Returns 0 on pass, 1 on regression."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--allowed-regression-pct", type=float, default=50.0)
    args = parser.parse_args()

    from pen_plotter.converters.defaults import register_default_converters
    from pen_plotter.converters.registry import registry
    from pen_plotter.persistence import init_db

    register_default_converters(registry)
    init_db()

    # Warmup runs absorb the first-call costs (template parse, vpype
    # import, …).
    _measure_bitmap(_bitmap_bytes(), args.warmup)
    _measure_vector(_svg_bytes(), args.warmup)

    bitmap_samples = _measure_bitmap(_bitmap_bytes(), args.runs)
    vector_samples = _measure_vector(_svg_bytes(), args.runs)
    measured: dict[str, dict[str, float]] = {
        "bitmap_photo": {k: _p95(v) for k, v in bitmap_samples.items()},
        "vector_svg": {k: _p95(v) for k, v in vector_samples.items()},
    }

    failed = False
    print("# perf gate report")
    for fixture, phases in REFERENCE_P95.items():
        print(f"\n## {fixture}")
        print("| phase | reference (ms) | measured (ms) | allowed (ms) | status |")
        print("|-------|----------------|---------------|--------------|--------|")
        for phase, ref in phases.items():
            obs = measured[fixture][phase]
            allowed = ref * (1 + args.allowed_regression_pct / 100)
            status = "OK" if obs <= allowed else "REGRESSION"
            if obs > allowed:
                failed = True
            print(f"| {phase} | {ref:.1f} | {obs:.1f} | {allowed:.1f} | {status} |")
    print()
    if failed:
        print("perf_gate: REGRESSION detected", file=sys.stderr)
        return 1
    print("perf_gate: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
