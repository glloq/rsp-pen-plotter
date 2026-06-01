# Environment variables

OmniPlot reads its runtime configuration from environment variables. The
appliance install writes them into `/etc/omniplot/.env.service` (mode
600) — edit there and `sudo systemctl restart omniplot`. For dev
servers, export them in the shell before `./start.sh`.

## Network

| Variable | Default | Effect |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Interface to bind. Set to `127.0.0.1` to restrict to localhost. |
| `PORT` | `8000` | UI + API port. |
| `OMNIPLOT_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allow-list. `*` is rejected at startup (can't combine with credentialed requests). |

## Authentication

| Variable | Default | Effect |
| --- | --- | --- |
| `OMNIPLOT_API_KEY` | unset | Machine-control + macro endpoints require this on `X-API-Key` (or `?token=` for WebSockets). Strongly recommended on a shared LAN. |
| `OMNIPLOT_REQUIRE_AUTH` | unset | When `1` / `true`, the service refuses to start with an empty `OMNIPLOT_API_KEY`. Pair with the variable above in production. |

## Storage

| Variable | Default | Effect |
| --- | --- | --- |
| `OMNIPLOT_DB` | `backend/data/omniplot.db` | SQLite database path (jobs, queue, audit, library). |
| `OMNIPLOT_PROFILES_DIR` | platform user dir | Where imported user profiles are stored. |
| `OMNIPLOT_STATIC_DIR` | `frontend/dist` | Override where the built UI is served from. |

## Tooling

| Variable | Default | Effect |
| --- | --- | --- |
| `OMNIPLOT_LIBREOFFICE_BIN` | first `libreoffice` / `soffice` on `PATH` | Override the LibreOffice binary used by the document converter. |
| `OMNIPLOT_GHOSTSCRIPT_BIN` | first `gs` on `PATH` | Override the Ghostscript binary used by the EPS converter. |
| `OMNIPLOT_POTRACE_BIN` | first `potrace` on `PATH` | Override the potrace binary used by `direct` vectorisation. |

## Deployment role

For multi-process deployments (see [`docs/deployment.md`](../docs/deployment.md)).

| Variable | Default | Effect |
| --- | --- | --- |
| `OMNIPLOT_ROLE` | `monolith` | One of `monolith`, `api`, `render`, `executor`, `telemetry`. The lifespan conditions which subsystems boot. |

## Updates

| Variable | Default | Effect |
| --- | --- | --- |
| `OMNIPLOT_DISABLE_UPDATE` | unset | When `1`, removes `POST /system/update` entirely. Use on appliances that should only be updated by hand. |

## Telemetry & SLO

| Variable | Default | Effect |
| --- | --- | --- |
| `OMNIPLOT_OTEL_ENABLED` | unset | When `1`, installs the OpenTelemetry tracer provider and emits spans for `convert_file`, `segment_and_render`, `optimize_svg`, `generate_gcode`. |
| `OMNIPLOT_OTEL_EXPORTER` | `console` if OTEL enabled | Where to send spans. `console` writes to stderr; `otlp` ships them to a collector defined by the standard `OTEL_EXPORTER_*` env vars. |
| `OMNIPLOT_SLO_EVAL_ENABLED` | unset | When `1`, the background SLO evaluator runs `evaluate_budgets` periodically and emits `slo_breach` log lines on breach. |
| `OMNIPLOT_SLO_EVAL_INTERVAL` | `60` (seconds) | Eval cadence. |

## Internal / dev only

| Variable | Default | Effect |
| --- | --- | --- |
| `OMNIPLOT_IR_ENABLED` | unset | When `1`, the pipeline writes a `GeometryIR` artifact alongside the SVG into `ir_artifact_cache`. Write-only today; the consumer ships next. |

## See also

- [`docs/getting_started.md`](../docs/getting_started.md)
- [`docs/deployment.md`](../docs/deployment.md)
- [Install on a Raspberry Pi](Install-on-a-Raspberry-Pi.md)
