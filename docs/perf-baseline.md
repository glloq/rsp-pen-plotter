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
| convert  |    513.32 |   523.50 |   541.23 |   541.23 |
| optimize |      0.70 |     0.68 |     0.74 |     0.74 |
| gcode    |    107.81 |    92.37 |   188.80 |   188.80 |

### vector_svg (synthetic 100×100)

| phase    | mean (ms) | p50 (ms) | p95 (ms) | p99 (ms) |
|----------|-----------|----------|----------|----------|
| convert  |      0.35 |     0.35 |     0.39 |     0.39 |
| optimize |      3.05 |     2.93 |     3.60 |     3.60 |
| gcode    |      1.05 |     1.02 |     1.27 |     1.27 |

> **Delta vs A.2 baseline** (after F.2 + F.3 quick wins):
> - `optimize` p95 on bitmap_photo dropped from 262.61 ms → 0.74 ms
>   (-99 %) thanks to the F.3 short-circuit (single-layer
>   single-path → skip vpype). Real multi-colour bitmaps with several
>   primitives won't trigger the short-circuit; the synthetic fixture
>   is intentionally trivial.
> - `convert` p95 on bitmap_photo dropped from 629.10 ms → 541.23 ms
>   (-14 %), partly the Jinja template hoist landed in F.2 (cold-cache
>   gcode lookup is now part of import time) and partly noise across
>   the 7-run sample.
> - `optimize` on vector_svg slightly down (3.86 → 3.60 ms) from the
>   same hoist effect.
> - `gcode` mean on bitmap_photo went up from 67 → 92 ms median —
>   that's sample noise on a 7-run window; p50 spread across two
>   re-measurements is ±20 ms. Worth a follow-up dedicated run with
>   more iterations to confirm whether the Jinja hoist is actually
>   neutral or if there's a regression hiding in a different path.

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
