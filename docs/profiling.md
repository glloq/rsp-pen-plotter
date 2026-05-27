# Profiling guide

Roadmap step **D.1**. The backend exposes two complementary profiling
paths: **`py-spy`** for CPU flamegraphs of a running process, and the
**OTel sub-step spans** (B.5) for endpoint-level latency without
needing a separate run.

The two tools answer different questions:

| Question                                           | Use                  |
|----------------------------------------------------|----------------------|
| "Which Python function dominates the bitmap path?" | `py-spy record`      |
| "How long did segmentation take on this request?"  | OTel spans           |
| "Is the live process stuck somewhere right now?"   | `py-spy top` (live)  |
| "Is there a regression between two refactors?"     | `scripts/perf_baseline.py` |

## py-spy

[py-spy](https://github.com/benfred/py-spy) is a **sampling profiler** —
it reads stack frames from a running process without instrumenting
the code, so the overhead is minimal and it's safe to attach in
production. Install with::

    pip install py-spy

### Record a flamegraph

`backend/scripts/profile.sh` wraps the common invocations. Start the
backend, then::

    cd backend
    scripts/profile.sh record --duration 30 --output flame.svg
    open flame.svg  # or send it to the team

The wrapper auto-detects the uvicorn process by default; override
with `OMNIPLOT_PID=<pid>` if you have several plotter backends
running on the same host.

### Live top

For a quick "what is it doing right now" check::

    scripts/profile.sh top

Same auto-PID logic.

### Reading a flamegraph

- Width = wall-clock cost. The widest function is the most expensive.
- Top of the stack = inner-most call (the one actually running).
- Hover (in a browser) for the exact percentages.
- Look for sustained tall columns: a deep stack that stays wide
  through many samples is the optimisation target. Wide-but-shallow
  is usually a hot loop in C extensions (numpy / vpype) and
  optimising the call site matters more than the function itself.

## OpenTelemetry sub-step spans

Already covered in `docs/observability.md`. In short, set
`OMNIPLOT_OTEL_ENABLED=1` + the OTLP exporter and the spans appear
in any OTel backend (Grafana Tempo, Jaeger, Signoz, …) with one
parent `pipeline.convert_file` and child spans for each phase
(`pipeline.bitmap.{load,preprocess,fit_within,segment,
drop_small_regions,merge_similar_colours,render_layer,
render_parallel,compose_svg}`).

For an ad-hoc check without a backend, set
`OMNIPLOT_OTEL_EXPORTER=console` and the spans print to stderr.

## scripts/perf_baseline.py

Macro-level reproducer. Runs the deterministic fixtures (a 128×128
two-tone PNG and a hand-written SVG) through the full pipeline N
times and emits a markdown table with p50/p95/p99 per phase.

    .venv/bin/python scripts/perf_baseline.py --runs 7 --warmup 2

Commit the new numbers to `docs/perf-baseline.md` whenever you ship
a change that affects the pipeline cost — phase D.2 will read the
delta to drive the optimisation report.

## Workflow for a perf investigation

1. Reproduce the cost with `scripts/perf_baseline.py` to anchor the
   "before" numbers.
2. Open the relevant OTel trace (or `OMNIPLOT_OTEL_EXPORTER=console`)
   to find which phase actually owns the time.
3. Attach `py-spy record` while replaying the same fixture to
   identify the hot function inside that phase.
4. Land the fix in a separate PR with the new `scripts/perf_baseline.py`
   table — the delta is the proof.
