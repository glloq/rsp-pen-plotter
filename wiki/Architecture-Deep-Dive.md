# Architecture deep dive

The architecture reference doc ([`docs/architecture.md`](../docs/architecture.md))
covers the *what*. This page covers the *why*, with the trade-offs that
shaped each layer.

## The seven layers, revisited

```
 ┌──────────────────────────────────────────────┐
 │ 1. Vue 3 UI            (browser)             │ ─┐
 │ 2. FastAPI orchestrator (Python, on the Pi)  │  │
 │ 3. Graphics + toolpath  (vpype)              │  │  Raspberry Pi
 │ 4. Persistent queue     (SQLite)             │ ─┘
 │ 5. Real-time motion     (Klipper / FluidNC)  │ ─── RP2040 / ESP32
 │ 6. Drivers              (TMC2209)            │ ─┐
 │ 7. Mechanics            (CoreXY)             │ ─┘  Hardware
 └──────────────────────────────────────────────┘
```

Layers 1–4 live in this repository. Layer 5 is firmware. Layers 6–7 are
hardware. The split between layer 4 and layer 5 is the **important
boundary**: everything above is portable to any Linux box, everything
below is real-time deterministic on a microcontroller.

## Why these technologies

The four [Architecture Decision Records](../docs/adr/README.md) give the
long answer. Short version:

- **SVG pivot** ([ADR-0001](../docs/adr/0001-svg-pivot.md)) — one
  format, every input converges on it, the rest of the pipeline doesn't
  care where the bytes came from.
- **vpype** ([ADR-0002](../docs/adr/0002-vpype-dependency.md)) — the
  pen-plotter pre-processing toolkit. Solving "merge lines, simplify,
  sort, optimise" from scratch is years of work; vpype already does it
  well.
- **Pydantic** ([ADR-0003](../docs/adr/0003-pydantic.md)) — runtime +
  type-time contract between the API and everything else. Pairs with
  TypeScript generation for the frontend.
- **SQLite** ([ADR-0004](../docs/adr/0004-sqlite.md)) — a single-process
  appliance doesn't need a server-class database; SQLite is fast,
  reliable, and survives `kill -9`.

## The SVG-pivot pipeline in detail

```
[Upload bytes]
     │
     ▼
[ConverterRegistry.for_mime(...)]              ← converters/registry.py
     │
     ▼
[Converter.convert(bytes, options)]
     │   one of: bitmap, svg, pdf, dxf, eps,
     │           document, text, markdown, html
     ▼
[ConversionResult.svg, .warnings]              ← converters/base.py
     │
     ▼
[Library store]                                ← persistence by SHA-256
     │
     ▼
[Editor places & edits]                        ← rerender pipeline
     │
     ▼
[Layer extraction]                             ← core/layers.py
     │
     ▼
[Per-layer toolpath optimisation]              ← vpype linemerge/linesimplify/linesort
     │
     ▼
[G-code generation (template or EBB)]          ← core/gcode.py · core/ebb.py
     │
     ▼
[Persistent queue]                             ← queue.py
     │
     ▼
[Hardware streamer]                            ← hardware/Streamer
     │
     ▼
[USB → MCU → motors]
```

Each arrow is a process boundary in terms of caching: the library is
keyed by the upload's SHA-256, the rerender by `(file_hash, settings_hash)`,
the resolved plan by `plan_hash`. So an operator who scrolls back to a
previous setting gets the cached render instantly.

## Why an internal IR is coming

The SVG pivot has one downside: it loses information that's expensive
to recompute. Curves get sampled to polylines; spline control points
disappear; algorithms that want pixel-perfect raster information have
to re-sample the source bitmap.

The `GeometryIR` artefact (opt-in via `OMNIPLOT_IR_ENABLED=1`) keeps a
richer representation alongside the SVG. The pipeline writes both today;
the rerender / optimise / generate stages will read the IR directly
once the consumer side ships. The SVG pivot will stay as the on-disk
canonical format for tooling interop.

## Backend / frontend contract

Pydantic models in `backend/pen_plotter/models.py` are the single source
of truth. A code-gen step produces TypeScript types under
`frontend/src/api/` from the OpenAPI schema. The CI build refuses to
ship if the two are out of sync.

See [`docs/contract_architecture.md`](../docs/contract_architecture.md)
for the wiring.

## Concurrency model

The backend is a single-process FastAPI app. Inside:

- a thread pool for CPU-heavy request handlers — upload/convert,
  rerender, optimize, analyze, generate, preflight and the system git
  subprocess all run via `run_in_threadpool`, so a long conversion never
  blocks the event loop (and the blocking subprocess calls to
  LibreOffice, Ghostscript and potrace ride along in those workers)
- an asyncio event loop for everything else (HTTP, WebSocket, serial)
- a single background task for the persistent queue worker, which
  throttles its SQLite progress checkpoints (every 50 lines / 2 s plus
  on every stream-state flip) so a per-`ok` fsync never lands on the loop
- a single background task for the SLO evaluator (when enabled)

There is no shared lock for *placements* — the operator owns them
serially. The lock that matters is the **hardware lock** held by the
queue worker; only one job streams at a time, and `POST /plotter/run`
is a 409 if the streamer is busy.

## Frontend state

Pinia stores, organised by domain:

- `job` — placements, the active variant, generate state
- `library` — file index + filters
- `plotter` — serial connection status, jog state
- `queue` — runs, pause/resume
- `macros` — saved macros
- `algorithms` — manifest + fallback snapshot
- `presets` — saved presets
- `ui` / `uiMode` — modal state, Assistant ⇆ Expert
- `toasts` — global notification bus
- `perf` — KPIs feeding the perf overlay
- `uploads` — global upload pool and progress

See [`docs/frontend.md`](../docs/frontend.md) for the component map.

## See also

- [`docs/architecture.md`](../docs/architecture.md)
- [`docs/adr/`](../docs/adr/README.md)
- [`docs/contract_architecture.md`](../docs/contract_architecture.md)
- [`docs/plugin-sdk.md`](../docs/plugin-sdk.md)
