r"""Compare the SVG-string pipeline against the typed-IR pipeline.

The v2 roadmap (TODO 2.1c) gates flipping ``OMNIPLOT_IR_ENABLED`` to
on-by-default on a perf audit run **on Pi-class hardware**. This script
is the automatable half of that audit: it times the two routes of each
phase on deterministic fixtures and prints the delta.

Routes compared per phase:

- optimize:  ``optimize_svg(svg)``            vs ``optimize_geometry_ir(ir)``
- gcode:     ``generate_gcode(svg, profile)`` vs ``generate_gcode_from_geometry(ir, profile)``

The IR is built once per fixture (``geometry_ir_from_svg``) outside the
timed section — in production it comes from the artifact cache, so its
construction cost is not part of the route being compared.

Usage (on the Pi, from ``backend/``)::

    .venv/bin/python scripts/perf_ir_compare.py --runs 9 --warmup 2

Decision rule (see docs/perf_pi_procedure.md): flip the default only if
the IR route's p95 is at parity or better on BOTH phases and both
dense-fixture variants.
"""

from __future__ import annotations

import argparse
import os
import tempfile
import time
from pathlib import Path
from statistics import median

os.environ.setdefault("OMNIPLOT_DB", str(Path(tempfile.gettempdir()) / "omniplot_ircmp.db"))

import math  # noqa: E402

# Import the converters package first: it participates in an import
# cycle with ``core.pdf_postprocess`` that only resolves cleanly in
# this direction (same order the app entrypoint uses).
import pen_plotter.converters  # noqa: E402, F401

from pen_plotter.core.gcode import (  # noqa: E402
    generate_gcode,
    generate_gcode_from_geometry,
)
from pen_plotter.core.toolpath import (  # noqa: E402
    optimize_geometry_ir,
    optimize_svg,
)
from pen_plotter.domain.ir.adapter import (  # noqa: E402
    content_sha256,
    geometry_ir_from_svg,
)
from pen_plotter.profiles import get_profile  # noqa: E402

_NS = (
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
)


def _fixture_simple() -> str:
    """Two nested squares in one layer — the baseline vector fixture."""
    return (
        f'<svg {_NS} viewBox="0 0 100 100">'
        '<g inkscape:label="black" stroke="#000000">'
        '<path d="M10,10 L90,10 L90,90 L10,90 Z" fill="none"/>'
        '<path d="M30,30 L70,30 L70,70 L30,70 Z" fill="none"/>'
        "</g></svg>"
    )


def _fixture_dense(paths_per_layer: int = 400, layers: int = 3) -> str:
    """A dense multi-layer plot — where route overhead actually shows.

    Hundreds of short polylines per layer approximate a hatched /
    stippled output, the case the optimizer and generator spend real
    time on. Deterministic (no RNG) so runs are comparable.
    """
    groups = []
    for layer in range(layers):
        parts = []
        for i in range(paths_per_layer):
            # Spread short strokes pseudo-uniformly with a fixed pattern.
            x = 5.0 + (i * 7.3) % 90.0
            y = 5.0 + (i * 11.7 + layer * 31.0) % 90.0
            dx = 2.0 + (i % 5)
            angle = (i * 0.7) % (2 * math.pi)
            x2 = x + dx * math.cos(angle)
            y2 = y + dx * math.sin(angle)
            parts.append(f'<polyline points="{x:.3f},{y:.3f} {x2:.3f},{y2:.3f}"/>')
        color = ["#000000", "#cc0000", "#0000cc"][layer % 3]
        groups.append(
            f'<g inkscape:label="layer-{layer}" stroke="{color}" fill="none">'
            + "".join(parts)
            + "</g>"
        )
    return f'<svg {_NS} viewBox="0 0 100 100">' + "".join(groups) + "</svg>"


def _time_ms(fn: object) -> float:
    start = time.perf_counter()
    fn()  # type: ignore[operator]
    return (time.perf_counter() - start) * 1000.0


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    idx = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
    return ordered[idx]


def main() -> int:
    """Run both routes per phase per fixture and print the comparison."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=7, help="Samples per route (default 7)")
    parser.add_argument("--warmup", type=int, default=2, help="Discarded warmup runs (default 2)")
    args = parser.parse_args()

    profile = get_profile("Custom CoreXY A3")
    assert profile is not None

    fixtures = {
        "simple (2 paths, 1 layer)": _fixture_simple(),
        "dense (1200 strokes, 3 layers)": _fixture_dense(),
    }

    print("# IR vs SVG route comparison")
    print()
    print(f"- runs per route: **{args.runs}** (+{args.warmup} warmup)")
    print()
    print("| fixture | phase | svg p50 | svg p95 | ir p50 | ir p95 | ir/svg p95 |")
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: |")

    for name, svg in fixtures.items():
        ir = geometry_ir_from_svg(svg, source_hash=content_sha256(svg.encode()))
        routes = {
            "optimize": (
                lambda svg=svg: optimize_svg(svg),
                lambda ir=ir: optimize_geometry_ir(ir),
            ),
            "gcode": (
                lambda svg=svg: generate_gcode(svg, profile),
                lambda ir=ir: generate_gcode_from_geometry(ir, profile),
            ),
        }
        for phase, (svg_fn, ir_fn) in routes.items():
            svg_samples: list[float] = []
            ir_samples: list[float] = []
            for i in range(args.warmup + args.runs):
                ms_svg = _time_ms(svg_fn)
                ms_ir = _time_ms(ir_fn)
                if i >= args.warmup:
                    svg_samples.append(ms_svg)
                    ir_samples.append(ms_ir)
            ratio = _p95(ir_samples) / _p95(svg_samples) if _p95(svg_samples) > 0 else 0.0
            print(
                f"| {name} | {phase} "
                f"| {median(svg_samples):.1f} | {_p95(svg_samples):.1f} "
                f"| {median(ir_samples):.1f} | {_p95(ir_samples):.1f} "
                f"| {ratio:.2f} |"
            )
    print()
    print("ir/svg p95 < 1.00 means the IR route is faster; the flip rule")
    print("requires <= 1.00 on every row (docs/perf_pi_procedure.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
