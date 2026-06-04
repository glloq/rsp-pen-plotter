# Getting started

There are two ways to run OmniPlot: the **appliance** path (recommended for a
Raspberry Pi running the plotter) and the **dev** path (hot-reload backend +
Vite frontend on a workstation).

## Quick appliance install (Raspberry Pi / Debian / Ubuntu)

One command. Clones the repo, installs every system package, Node.js, the
Python toolchain (`uv`), builds the frontend and — with `--service` — enables
a `systemd` unit that survives reboots:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/glloq/rsp-pen-plotter/main/bootstrap.sh) --service
```

Then open `http://<pi-ip>:8000` from any device on the LAN.

Without `--service` the installer stops short of `systemd`; launch manually
with `./start.sh`. If you already cloned the repo, `./install.sh --service`
does the same thing locally.

### What the installer does

Idempotent — every step is skipped when already satisfied.

1. installs `potrace`, `ghostscript`, `libreoffice-writer` via apt
   (needed by the bitmap, EPS and DOCX converters)
2. installs Node.js 20 via NodeSource if missing
3. installs `uv` (the Python toolchain) into `~/.local/bin` if missing
4. `uv sync` for the backend deps
5. `npm ci && npm run build` for the frontend
6. on `--service`: writes the systemd unit, adds the user to `dialout`
   (for `/dev/ttyUSB*` access), enables and starts `omniplot.service`

Flags: `--service` (install + enable the systemd unit), `--no-system-deps`
(skip the apt steps for custom Python / Node setups).

### Managing the service

```bash
sudo systemctl status omniplot      # check state
sudo journalctl -u omniplot -f      # follow logs
sudo systemctl restart omniplot     # after editing .env.service
```

`./install-service.sh` writes a `.env.service` (mode 600) — edit it to
override `HOST`, `PORT`, `OMNIPLOT_API_KEY`, `OMNIPLOT_DB`,
`OMNIPLOT_CORS_ORIGINS`, etc. Full list of variables in the section below.

---

## Dev install (workstation, hot reload)

### Prerequisites

- Python 3.12+
- Node.js 20+ (the repo's `.nvmrc` pins it — `nvm use` honours that)
- [`uv`](https://github.com/astral-sh/uv) for Python dependency management
- System tools used by some converters (only when you exercise those formats):
  - `potrace` — bitmap vectorisation
  - `ghostscript` — EPS / AI rasterisation
  - `libreoffice` — DOCX / ODT / RTF conversion
- A pen plotter for the hardware features (a DIY CoreXY or an AxiDraw); the
  full software chain runs and is validated in the simulator without any
  hardware.

## Backend

```bash
cd backend
uv sync --extra dev                        # install dependencies + dev extras (ruff, mypy, pytest)
uv run uvicorn pen_plotter.main:app --reload
```

CI runs `uv sync --extra dev` then calls every quality gate through
`uv run …` to make sure the version from `.venv` is the one being
exercised. Reproduce locally the same way (don't rely on globally
installed `ruff`, `mypy`, or `pytest` shims).

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
| `OMNIPLOT_API_KEY` | unset | When set, every router (except `/health`) requires the value on `X-API-Key` or `?token=`. Leave unset for single-machine development; set a 32+ char secret before exposing the appliance to a shared LAN. See `docs/deployment.md` § Production hardening. |
| `OMNIPLOT_REQUIRE_AUTH` | unset | Truthy (`1`/`true`) makes the service refuse to start if `OMNIPLOT_API_KEY` is empty. Pair the two in production so an accidental restart cannot silently come up with the controls open. |
| `OMNIPLOT_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allow-list. `*` is rejected at startup because it cannot legally combine with credentialed requests. |
| `OMNIPLOT_DISABLE_UPDATE` | unset | When `1`, removes the `POST /system/update` endpoint entirely. Use on appliances that should only be updated by hand on the host. |
| `OMNIPLOT_MAX_UPLOAD_MB` | `50` | Per-request body cap for uploads (POST `/upload`, POST `/files`). Streams reject the request before the body is fully buffered. |
| `OMNIPLOT_RATE_LIMIT_ENABLED` | `1` | Toggle the in-process token-bucket rate limiter. Set to `0` for load tests. |
| `OMNIPLOT_RATE_LIMIT_RPM` | `600` | Steady-state requests per minute, per client IP (≈10 req/s). |
| `OMNIPLOT_RATE_LIMIT_BURST` | `60` | Extra tokens the bucket can hold for short bursts (e.g. wizard click-through). |
| `OMNIPLOT_FAKE_HARDWARE` | unset | When `1`, the plotter controller uses an in-process mock transport instead of opening a serial port. Lets E2E tests drive the full operator workflow without hardware. |

CORS is preconfigured to allow the Vite dev origin `http://localhost:5173`.

## Frontend

```bash
cd frontend
nvm use                                    # respect the repo's .nvmrc (Node 20)
npm ci                                     # exact dependencies from package-lock.json
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
npm run lint            # eslint
npm run format:check    # prettier --check
npm run test            # vitest
npm run build           # vue-tsc --noEmit type check + production build
npm run e2e:install     # download Playwright's chromium (once per machine)
npm run e2e             # playwright test (spawns the Vite dev server)
```

CI runs the same scripts; reproducing a failure locally is a matter of
matching the Node version in `.nvmrc` (`nvm use`) and running the
command. Quality gates land as separate CI jobs (lint, format,
type-check, unit, build, e2e), so a single failure tells you exactly
where to look.

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
