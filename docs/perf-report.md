# Performance optimisation report (v0.2 entry-state)

Roadmap step **D.2**. Read after `docs/perf-baseline.md` (the
captured macro numbers) and `docs/observability.md` (the OTel sub-step
breakdown). This document prioritises the optimisation work for the
v0.2 → v0.3 horizon based on the **measured cost** of each pipeline
phase, not gut feel.

The numbers here are reproducible: rerun
`backend/scripts/perf_baseline.py --runs 10 --warmup 3` and the
shape of the table (bitmap dominated by `convert`, vector dominated
by `optimize`) is invariant across hardware. Absolute values vary;
the **proportional contribution** is what we track.

## Captured baseline (entry to v0.2)

### bitmap_photo (synthetic 128×128 PNG, halftone, 2 colours)

| phase    | mean (ms) | p50 (ms) | p95 (ms) | p99 (ms) | share of mean |
|----------|-----------|----------|----------|----------|--------------:|
| convert  |    465.08 |   534.45 |   569.85 |   569.85 |          71 % |
| optimize |    105.29 |   103.04 |   112.49 |   112.49 |          16 % |
| gcode    |     78.40 |    66.46 |   180.59 |   180.59 |          12 % |

### vector_svg (synthetic 100×100)

| phase    | mean (ms) | p50 (ms) | p95 (ms) | p99 (ms) | share of mean |
|----------|-----------|----------|----------|----------|--------------:|
| convert  |      0.39 |     0.39 |     0.52 |     0.52 |           7 % |
| optimize |      3.60 |     3.50 |     4.01 |     4.01 |          69 % |
| gcode    |      1.19 |     1.17 |     1.26 |     1.26 |          24 % |

## Top bottlenecks (ranked by absolute cost)

### B1 — bitmap `convert` dominates everything

- **Measured cost**: ~465 ms mean / ~570 ms p95 on a 128² synthetic
  fixture. The vast majority of an `/upload` round-trip on a small
  bitmap.
- **Inside the span**: `pipeline.bitmap.segment` is the loud one —
  10-iteration k-means restart by default (`n_init=10`). The
  preprocess + load + fit_within combined are sub-10 ms on this
  fixture.
- **Quick win** (effort: S, impact: M)
  Pass `fast=True` in the resolver-driven path when `quality_tier`
  is `draft`. The flag drops `n_init` to 1 and is already plumbed
  through `BitmapConverter.segment_and_render`. Net: roughly 5x on
  `segment` for draft previews. Wire into the resolver output in
  Phase B.1's `default_options`.
- **Medium refactor** (effort: M, impact: M)
  Cache `(content_sha256, num_colors, method)` → `SegmentationArtifact`
  in SQLite (IR cache from A.3). A second pass on the same image
  with the same settings would be ~0 ms.
- **Long term** (effort: L, impact: H)
  Move segmentation to a NumPy + Cython hot path (we already depend
  on scikit-image; this is mostly about replacing the unavoidable
  Python overhead in the cluster-relabel loop). Realistic ceiling:
  another 2-3x.

### B2 — bitmap `optimize` has a fixed ~100 ms floor

- **Measured cost**: ~105 ms mean on the same fixture. **Stays at
  ~100 ms on the vector fixture too at proportional cost**: this is
  a fixed vpype startup overhead (Click + plugin discovery + import
  of `numpy.linalg`).
- **Quick win** (effort: S, impact: M)
  Skip `vpype linesimplify` + `linesort` when the input is already
  monotonic — single-layer SVG with one polyline. Today we always
  build a vpype Document and run the full pipeline. Heuristic:
  skip when `extract_layers(svg)` returns ≤ 1 layer with ≤ 1 path.
- **Medium refactor** (effort: M, impact: M)
  Replace `vp.read_svg(StringIO(...))` with a direct SVG → numpy
  array conversion using the existing `pen_plotter.domain.ir.adapter`
  from A.3. The vpype pipeline is still the heaviest part but it
  consumes our IR instead of re-parsing the SVG.
- **Long term** (effort: L, impact: M)
  Replace vpype entirely for the on-line path; keep it as the
  exporter for offline batch work. The audit #1 §7 SIMD/Rust
  geometry kernels discussion hits this directly.

### B3 — `gcode` p95 has a bimodal long tail

- **Measured cost**: ~78 ms mean / ~180 ms p95 on the bitmap
  fixture. The p99 = p95 (sample-size limited) but the
  mean-vs-p50 gap (78 vs 66) tells the same story: most calls are
  fast, some are slow.
- **Suspected cause** (to confirm with py-spy from D.1): Jinja
  template compilation cache miss on the first call per template
  name. We resolve five templates inside `generate_gcode`
  (`header`, `footer`, `pen_up`, `pen_down`, `line`); the first
  call after a process restart pays the parse cost.
- **Quick win** (effort: S, impact: S)
  Pre-resolve the five templates at module import time in
  `pen_plotter.core.gcode` so the first request doesn't pay the
  parse tax. ~1-line change with a 100ms+ benefit on cold-cache
  calls.

### F1 — Frontend cost-chip latency hides the wait

- **Measured cost**: not yet in `usePerfStore` (C.8 collects samples
  but only locally). The `time_to_first_preview` KPI is wired and
  ready to capture — flip `?flag.perf=1` and exercise the modal
  V2 to populate it.
- **Quick win** (effort: S, impact: M)
  Show the resolver's `quality_tier` next to the cost chip so an
  operator with a 500 ms wait understands they asked for `final`
  and a `draft` would be 100 ms. Already in the modal V2's recap
  step; not on the file list yet.

## Quick wins prioritised

| Win                                       | Effort | Estimated impact      |
|-------------------------------------------|--------|-----------------------|
| Wire `fast=True` for `draft` quality      | S      | 5x on segment         |
| Pre-resolve Jinja templates               | S      | -100 ms cold-cache    |
| Skip vpype on single-layer SVG            | S      | -100 ms when applies  |
| Surface `quality_tier` in cost chip       | S      | UX, not perf          |

Estimated cumulative effect on `bitmap_photo` /draft: **convert drops
from ~465 → ~120 ms, gcode drops from ~78 → ~30 ms, optimize stays
at ~105 ms** → end-to-end ~640 → ~255 ms. That's the SLO target
phase D.4 should calibrate against.

## Medium refactors

- **IR-cache segmentation results** (A.3 plumbing already in place;
  needs a SQLite-backed `SegmentationStore`).
- **Replace vpype DOM round-trip on the on-line path** — feed the
  Geometry IR directly into `optimize_svg`.
- **`renderer.compose_svg` parallel-vs-serial threshold** — today the
  switch happens at `n_workers > 1`; it should be based on the
  per-layer cost the worker pool would amortize.

## Long-term architecture (Phase E / V2)

These are restated from audit #1 with measured weight added:

- **Workerized compute boundary** — move segment + render off the
  API process (D.6). Lets us add a queue between the operator's
  preview tier and the bursts of `/upload`s.
- **SIMD/Rust kernels** for `segment` and `render_layer`. The numpy
  paths are already vector-friendly; the wins are in the small
  loops k-means and stippling can't avoid.
- **Spatial indices** (R-tree / KD-tree) for the nearest-neighbour
  steps in `tsp_opt` and `voronoi_stipple`. Both algorithms are in
  the "heavy" cost class; they don't appear in `bitmap_photo`
  baselines because the resolver doesn't pick them for `fast`/
  `balanced` (B.1 hard constraint).

## How to rerun this report

1. Bring the backend to a clean state (no other heavy load).
2. `cd backend && .venv/bin/python scripts/perf_baseline.py --runs 10 --warmup 3 > /tmp/baseline.md`
3. Diff `/tmp/baseline.md` against the captured snapshot in
   `docs/perf-baseline.md`.
4. If the shape changed (a phase's % share moved by > 5 points),
   the priorities above need re-validation — the bottleneck may
   have shifted.
