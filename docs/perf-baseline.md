# Performance baseline (v0.1)

> Captured at the start of the v0.2 refactor (roadmap step **A.2**) so
> subsequent phases can quote a delta. **Do not edit by hand to make
> numbers look good** — rerun `scripts/perf_baseline.py` and commit the
> fresh output.

## How to reproduce

```sh
cd backend
.venv/bin/python scripts/perf_baseline.py --runs 7 --warmup 2
```

The script generates **deterministic synthetic fixtures** (a two-tone
128×128 PNG and a small hand-written SVG) so this baseline does not
depend on user-supplied content. Real-world fixtures (large photos,
multi-page PDFs, complex SVGs) will be added in phase B alongside the
`AlgorithmPolicyResolver` matrix.

Timings are wall-clock milliseconds per pipeline phase. Phases:

- **convert** — `convert_file` (MIME dispatch + converter + sanitize + extract layers)
- **optimize** — `optimize_svg` (vpype linemerge / linesimplify / linesort)
- **gcode** — `generate_gcode` (Jinja templates + transform)

## Snapshot

> Run on the development container; absolute numbers vary with hardware,
> but **the shape** (bitmap_photo dominated by `convert`, vector_svg
> dominated by `optimize`) is the property we'll track across refactors.

- runs per fixture: **7**
- warmup iterations: **2**

### bitmap_photo (synthetic 128×128 PNG)

| phase    | mean (ms) | p50 (ms) | p95 (ms) | p99 (ms) |
|----------|-----------|----------|----------|----------|
| convert  |    557.48 |   550.86 |   629.10 |   629.10 |
| optimize |    129.09 |   106.28 |   262.61 |   262.61 |
| gcode    |     68.06 |    67.37 |    73.04 |    73.04 |

### vector_svg (synthetic 100×100)

| phase    | mean (ms) | p50 (ms) | p95 (ms) | p99 (ms) |
|----------|-----------|----------|----------|----------|
| convert  |      0.38 |     0.38 |     0.44 |     0.44 |
| optimize |      3.63 |     3.61 |     3.86 |     3.86 |
| gcode    |      1.17 |     1.17 |     1.26 |     1.26 |

## First read

Two structural observations that motivate the rest of the roadmap:

1. **`convert` on a bitmap is the dominant cost** — the halftone
   render on a 128² fixture already costs ~0.5 s, three orders of
   magnitude more than the same phase on vector input. Phase B (resolver
   + segmentation) and D (workerized compute) are aimed straight at
   this.
2. **`optimize` on a bitmap takes >100 ms even on a tiny input** —
   suggesting the vpype line-merge/sort pass has a fixed cost that
   dominates on small geometry; worth profiling once py-spy is wired in
   (step D.1).

These observations are **not blockers** but they sketch where the
biggest wins of the refactor will land. SLO targets (`docs/ROADMAP_V0.2.md`
§6) will be calibrated from this table.
