# Getting Started

## Prerequisites

- Python 3.12+
- Node.js 20+
- [`uv`](https://github.com/astral-sh/uv) for Python dependency management
- System tools used by some converters (optional, only for those formats):
  - `potrace` — bitmap vectorization
  - `ghostscript` — EPS/AI rasterization
  - `libreoffice` — DOCX/ODT/RTF conversion
- A pen plotter for the hardware features (a DIY CoreXY or an AxiDraw); the full
  software chain runs and is validated in the simulator without any hardware.

## Backend

```bash
cd backend
uv sync                                    # install dependencies (incl. dev)
uv run uvicorn pen_plotter.main:app --reload
```

The API serves on `http://localhost:8000`. Check it with
`curl http://localhost:8000/health`.

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OMNIPLOT_DB` | `omniplot.db` | SQLite job-history database path |
| `OMNIPLOT_PROFILES_DIR` | platform user dir | Where imported user profiles are stored |
| `OMNIPLOT_IR_ENABLED` | unset | When `1`, the converter pipeline builds a `GeometryIR` artifact alongside the SVG and persists it in the `ir_artifact_cache` table. Write-only today; the IR-native render/optimize path consumes it next. |
| `OMNIPLOT_OTEL_ENABLED` | unset | When `1`, installs the OpenTelemetry tracer provider and emits spans for `convert_file`, `segment_and_render`, `optimize_svg`, `generate_gcode`. Pair with `OMNIPLOT_OTEL_EXPORTER=console` to see them in stderr. |
| `OMNIPLOT_SLO_EVAL_ENABLED` | unset | When `1` and the role serves HTTP, the lifespan starts the background SLO evaluator. It re-runs `evaluate_budgets` every `OMNIPLOT_SLO_EVAL_INTERVAL` seconds (default 60) on the accumulated samples and emits `slo_breach` log lines on breach. |
| `OMNIPLOT_ROLE` | `monolith` | Deployment role: `monolith`, `api`, `render`, `executor`, or `telemetry`. The lifespan conditions which subsystems boot per role. See `docs/deployment.md`. |

CORS is preconfigured to allow the Vite dev origin `http://localhost:5173`.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

The UI serves on `http://localhost:5173`. The API base URL defaults to
`http://localhost:8000` and can be overridden with the `VITE_API_URL`
environment variable (set it explicitly in production).

## Tests and quality gates

Backend:

```bash
cd backend
uv run ruff check .     # lint (E, F, I, N, UP, B, D)
uv run mypy             # strict type checking of pen_plotter
uv run pytest           # full test suite
```

Frontend:

```bash
cd frontend
npm run test            # vitest
npm run build           # vue-tsc --noEmit type check + production build
```

## Typical workflow

1. Upload a file → the matching converter normalizes it to the SVG pivot.
2. Inspect and toggle layers, assign pen slots, set per-layer speed/simplify.
3. Optimize toolpaths (vpype) and review the travel-reduction metrics.
4. Generate G-code against a machine profile and preview it.
5. Validate in the simulator, then connect to the plotter and stream the job.

## v0.2 UI surfaces

The v0.2 release adds several new operator-facing surfaces. Most are
visible by default after the wiring phase; a few stay behind URL
feature flags so they can be QA'd without disrupting muscle-memory.

| Surface | Where | Activation |
| --- | --- | --- |
| AssistantModeToggle (Assisté / Expert) | App header | always visible |
| Workspace switcher + Save as / Rename / Remove menu | App header | always visible |
| Workshop button | App header | always visible; click to open Workshop Mode |
| Modal V2 (beta) toggle | App header | always visible; click to switch the Edit modal to the 6-step V2 |
| WorkspaceRail (right column) | App main grid | shows when the active workspace has v2 panels (Beginner ships with `queue` + `magazine` + `machine_telemetry`; Pro adds inspectors) |
| Compare drawer | Floating bottom-left button | always visible; shows empty state when no second variant |
| ManifestFallbackBanner | Top of app, under header | auto-shows when the backend's algorithm manifest can't be reached |
| SLO + Manifests panels | Settings drawer | always available tabs |
| WorkshopMode (full-screen run cockpit) | Body | toggled via header Workshop button or `?flag.workshopMode=1` |
| PerfOverlay | Bottom-right chip | dev tool — enable via `?flag.perf=1` |

URL feature flags persist into `localStorage` once toggled. Override
in either direction with `?flag.<name>=0` or `?flag.<name>=1`:

| Flag | Effect |
| --- | --- |
| `modalV2` | Switches the Edit modal to the V2 6-step flow. |
| `workshopMode` | Opens the full-screen run cockpit. |
| `perf` | Shows the live KPI overlay (TTFP, refresh, slow interactions, errors). |

Keyboard shortcuts (see `docs/shortcuts.md` for the full list):

| Combo | Action |
| --- | --- |
| `Ctrl/Cmd + M` | Toggle Assisted / Expert mode |
| `Ctrl/Cmd + P` | Toggle perf overlay |
| `Ctrl/Cmd + K` | Pause active run |
| `Ctrl/Cmd + R` | Resume active run |
| `Ctrl/Cmd + Enter` | Modal V2: next step (or Generate on the last step) |
| `Ctrl/Cmd + Backspace` | Modal V2: previous step |

Shortcuts never intercept keystrokes that target an input,
textarea, or contenteditable surface — typing in a form always
behaves normally.
