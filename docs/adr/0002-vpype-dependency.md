# 0002 — Use vpype for layout, optimization, and G-code emission

- **Status**: accepted
- **Date**: 2024-09 (back-dated)

## Context

Plotting an SVG involves more than rendering polylines. It needs:

- **Layout primitives**: translate, scale, rotate, page bounds, multi-up.
- **Toolpath optimization**: reorder strokes to minimize travel, merge
  collinear segments, simplify Bézier curves to polylines within a chord
  tolerance.
- **G-code emission**: turn polylines into `G0` / `G1` with pen-up / pen-down
  commands, respecting a per-machine profile (drawing speed, travel speed,
  acceleration, arc support).

We had three options:

1. **Build it ourselves.** Write the simplifier, the TSP-ish optimizer, the
   layer-aware travel reducer, the G-code emitter. Maintain them. Test them
   against pathological inputs. Fix the long tail of edge cases (z-fighting
   between coincident strokes, self-intersecting paths, multi-layer pen
   order).
2. **Use vpype as a library.** Python toolchain explicitly designed for
   pen-plotter workflows. Mature TSP / 2-opt optimizers, vector simplifier,
   layout primitives, and G-code emission via the `vpype-gcode` plugin /
   our own Jinja templates layered on top.
3. **Use vpype as a CLI**, shelling out per job. Same library, but stitched
   together via subprocess calls.

## Decision

Use vpype **as a library** (option 2) for the optimization / layout layers
of the pipeline.

We keep our **own G-code emission** layer (Jinja templates per dialect:
GRBL, Marlin, Klipper, EBB) because:

- vpype-gcode's templates are flexible but not flexible enough for the
  per-profile knobs the operator picks (acceleration M204, pause policy
  injection, EBB serial conventions).
- Our golden-G-code regression tests exercise the templates directly; if
  vpype upgrades changed the emitter output, we'd lose CI coverage.

Pre-rendering optimization (simplify + reorder) is delegated to vpype via
`core/optimize.py`. The L2 lot in the audit captured `optimize` +
`simplify_tolerance_mm` in the `PrintPlan` pivot so each layer can carry
its own tuning.

## Consequences

### Positive

- **Don't reinvent toolpath optimization.** vpype's TSP-with-2-opt
  reorderer is among the best in class for pen plotters; we get it for
  free.
- **Aligns with the broader pen-plotter ecosystem.** Files plotters in the
  field (AxiDraw, NextDraw, custom CoreXY rigs) tend to assume vpype-style
  toolchains, so swapping our pre-render for `vpype simplify`-equivalent
  knobs is one less context shift for operators arriving from those tools.
- **Layers map cleanly.** vpype's "layers" concept is exactly our pivot's
  Inkscape-labelled `<g>` groups.

### Negative

- **Heavy install footprint.** vpype pulls in shapely, scipy, matplotlib's
  text rendering bits, and a few C extensions. The Pi image is correspondingly
  larger; we accept it.
- **Hard dependency on vpype's API stability.** vpype's public API has
  moved between 1.x and 2.x; we pin a specific minor version in
  `pyproject.toml` and treat vpype bumps as breaking-change PRs with a
  full golden-test re-run.
- **Some operations are slower than a bespoke implementation would be.**
  vpype runs general-purpose code; for the bitmap converter's
  per-cluster render we sidestep vpype and emit raw `<path>` directly
  inside the converter (`converters/bitmap/render.py`), then re-enter
  vpype's pipeline only for the layer-level optimize pass.
- **Long-tail vpype bugs surface in our pipeline.** Self-intersection
  handling, the `linemerge` tolerance, and a few corner cases in
  `linesort` have all bitten us. Each fix lives as a small monkey-patch
  in our adapter rather than a vpype fork.

## What we still own

The G-code emitter (`core/gcode.py` + Jinja templates) and the streaming
layer (`core/ebb.py`, the serial bridge to Klipper) are ours. vpype's
boundary stops at "produce optimized polylines"; everything after that is
project-specific.

## Alternatives we still reject

Building our own optimization stack is a project of its own — months of
work plus a long debug tail. The `flatpath`-class libraries (svgpathtools,
shapely directly) handle the primitives but not the pen-aware reordering;
we'd end up reimplementing vpype.

Shelling out to vpype CLI would add subprocess overhead per job and lose
the ability to short-circuit when the input is trivially small. We keep
vpype as a Python-level dependency.
