# OmniPlot documentation

This folder is the reference manual for OmniPlot — a universal pen plotter
studio that turns any file (images, PDFs, documents, SVG, text, raw G-code)
into plotted output on any pen plotter. Long-form guides, tutorials and
recipes live in the [`wiki/`](../wiki/Home.md) folder instead.

## Where to start

- New to the project? Read the [top-level README](../README.md) for a
  one-page overview with screenshots.
- Want to install on a Raspberry Pi? Jump to
  [`getting_started.md`](getting_started.md).
- Building a new plotter profile? See
  [`profile_format.md`](profile_format.md).

## Contents

### Use

| Document | What it covers |
| --- | --- |
| [getting_started.md](getting_started.md) | One-line Pi install, dev setup, environment variables, quality gates |
| [shortcuts.md](shortcuts.md) | Keyboard shortcuts and UI feature flags |
| [presets.md](presets.md) | Saving and reusing edit presets |
| [deployment.md](deployment.md) | Production hardening — auth, CORS, multi-role deployment |

### Build

| Document | What it covers |
| --- | --- |
| [architecture.md](architecture.md) | System layers, the SVG-pivot pipeline, module map |
| [api_reference.md](api_reference.md) | Every REST endpoint and the WebSocket message shape |
| [converters.md](converters.md) | Supported input formats and the 27+ raster algorithms |
| [adding_a_converter.md](adding_a_converter.md) | How to add support for a new input format |
| [profile_format.md](profile_format.md) | Machine profile YAML schema and the bundled examples |
| [hardware_streaming.md](hardware_streaming.md) | Serial transport, the G-code streamer, EBB, templates |
| [tool_change_mechanisms.md](tool_change_mechanisms.md) | How pen swaps are handled across firmwares |
| [frontend.md](frontend.md) | Vue component map, Pinia stores, i18n, SVG safety |
| [plugin-sdk.md](plugin-sdk.md) | Plugin architecture and extension points |
| [contract_architecture.md](contract_architecture.md) | Shared contracts (Pydantic + TS types) |

### Operate

| Document | What it covers |
| --- | --- |
| [observability.md](observability.md) | Logging, metrics, OpenTelemetry, SLO evaluator |
| [audit_report.md](audit_report.md) | Codebase audit findings and the fixes applied |
| [perf-baseline.md](perf-baseline.md) | Reference performance numbers |
| [perf-report.md](perf-report.md) | Latest performance report |
| [profiling.md](profiling.md) | How to profile a slow conversion or render |

### Plan

| Document | What it covers |
| --- | --- |
| [ROADMAP_V0.2.md](ROADMAP_V0.2.md) | What ships in the next release |
| [TODO.md](TODO.md) | Open backlog items |
| [adr/](adr/README.md) | Architecture Decision Records — load-bearing structural choices |

### Assets

| Path | Purpose |
| --- | --- |
| [images/interface-overview.svg](images/interface-overview.svg) | Main UI illustration (used in the top-level README) |
| [images/editor.svg](images/editor.svg) | Editor wizard illustration |
| [images/file-types.svg](images/file-types.svg) | Supported formats overview |
| [images/workflow.svg](images/workflow.svg) | Five-step workflow diagram |

## Quick links

- Repository root [README](../README.md)
- Long-form [`wiki/`](../wiki/Home.md) — tutorials, recipes, troubleshooting
- Backend package: `backend/pen_plotter/`
- Frontend app: `frontend/src/`
