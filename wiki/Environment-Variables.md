# Environment variables

OmniPlot reads its runtime configuration from environment variables. The
appliance install (`install-service.sh`) writes them into
`<repo>/.env.service` (mode 600) — edit there and
`sudo systemctl restart omniplot`. For dev servers, export them in the
shell before `./start.sh`.

## Network

| Variable | Default | Effect |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Interface to bind. Set to `127.0.0.1` to restrict to localhost. |
| `PORT` | `8000` | UI + API port. |
| `OMNIPLOT_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allow-list. `*` is rejected at startup (can't combine with credentialed requests). When no API key is set, this list is also consulted by the cross-origin write guard: state-changing requests carrying an `Origin` header that matches neither the request `Host` nor this list get a 403. |

## Authentication

| Variable | Default | Effect |
| --- | --- | --- |
| `OMNIPLOT_API_KEY` | unset | Machine-control + macro endpoints require this on `X-API-Key` (or `?token=` for WebSockets). Strongly recommended on a shared LAN. |
| `OMNIPLOT_REQUIRE_AUTH` | unset | When `1` / `true`, the service refuses to start with an empty `OMNIPLOT_API_KEY`. Pair with the variable above in production. |

## Storage

| Variable | Default | Effect |
| --- | --- | --- |
| `OMNIPLOT_DB` | `backend/data/omniplot.db` | SQLite database path (jobs, queue, audit, library). |
| `OMNIPLOT_FILES_DIR` | `backend/data/files` | Where the file library stores originals, normalized SVGs and previews. |
| `OMNIPLOT_MACROS_FILE` | `backend/data/macros.json` | JSON store for user macros. |
| `OMNIPLOT_USER_PRESETS` | `backend/data/user_presets.json` | JSON store for user-created presets. |
| `OMNIPLOT_PROFILES_DIR` | platform user dir | Where imported user profiles are stored. |
| `OMNIPLOT_TIMELAPSE_DIR` | `backend/data/timelapses` | Where timelapse recordings (frames, `video.mp4`, `meta.json`) are written, one folder per recording. |
| `OMNIPLOT_STATIC_DIR` | `frontend/dist` | Override where the built UI is served from. |

## Tooling

The external binaries OmniPlot calls (`libreoffice` / `soffice`, `gs`,
`potrace` for the converters, and `ffmpeg` to assemble timelapses) are
resolved from `PATH` via `shutil.which` — there is no per-binary override
variable. Install them where `PATH` finds them.

## Uploads, rate limiting & caches

| Variable | Default | Effect |
| --- | --- | --- |
| `OMNIPLOT_MAX_UPLOAD_MB` | `50` | Per-request body cap for `POST /upload` and `POST /files` (413 beyond it). |
| `OMNIPLOT_RATE_LIMIT_ENABLED` | `1` | Toggle the in-process token-bucket rate limiter. Set to `0` for load tests. |
| `OMNIPLOT_RATE_LIMIT_RPM` | `600` | Steady-state requests per minute, per client IP (≈10 req/s). |
| `OMNIPLOT_RATE_LIMIT_BURST` | `60` | Extra tokens for short bursts (wizard click-throughs). |
| `RERENDER_CACHE_SIZE` | `64` | LRU cap for the bitmap segmentation cache (clamped to 4–256). |

## Logging

| Variable | Default | Effect |
| --- | --- | --- |
| `OMNIPLOT_LOG_LEVEL` | `INFO` | Root log level (`DEBUG`, `INFO`, `WARNING`, …). |
| `OMNIPLOT_LOG_FORMAT` | `json` | `json` for structured lines, `text` for the human-friendly legacy format. |

## Hardware

| Variable | Default | Effect |
| --- | --- | --- |
| `OMNIPLOT_FAKE_HARDWARE` | unset | When `1` / `true`, the controller attaches an in-process mock transport instead of opening a serial port. Used by E2E tests to drive the full operator workflow without a plotter. |

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
| `OMNIPLOT_OTEL_EXPORTER` | `otlp` | Where to send spans. `otlp` ships them to `OMNIPLOT_OTLP_ENDPOINT`; `console` pretty-prints them to stderr (handy in dev). |
| `OMNIPLOT_OTLP_ENDPOINT` | `http://localhost:4318/v1/traces` | OTLP/HTTP collector endpoint used when the exporter is `otlp`. |
| `OMNIPLOT_SERVICE_NAME` | `omniplot-backend` | `service.name` on the OTel resource. |
| `OMNIPLOT_SLO_EVAL_ENABLED` | unset | When `1`, the background SLO evaluator runs `evaluate_budgets` periodically and emits `slo_breach` log lines on breach. |
| `OMNIPLOT_SLO_EVAL_INTERVAL` | `60` (seconds) | Eval cadence (floored at 5 s). |

## Installer & maintenance scripts

These are read by the shell scripts, not the backend:

| Variable | Script | Default | Effect |
| --- | --- | --- | --- |
| `OMNIPLOT_REPO` | `bootstrap.sh` | `https://github.com/glloq/rsp-pen-plotter.git` | Repo URL to clone. |
| `OMNIPLOT_BRANCH` | `bootstrap.sh` | `main` | Branch to check out. |
| `OMNIPLOT_DEST` | `bootstrap.sh` | `$HOME/rsp-pen-plotter` | Local clone target. |
| `OMNIPLOT_PYTHON` | `install.sh` | `python3` | Pin a Python 3.12+ interpreter for the venv fallback. |
| `OMNIPLOT_SKIP_NODE` | `install.sh` | unset | Non-empty skips Node.js install attempts (errors out if Node 20+ is missing). |
| `OMNIPLOT_HEALTH_URL` | `update.sh` | `http://127.0.0.1:$PORT/health` | Override the post-restart health probe URL. |
| `OMNIPLOT_UPDATE_REEXEC` | `update.sh` | unset | Internal guard set when the script re-executes its updated self; prevents an infinite re-exec loop. Don't set it yourself. |

## Internal / dev only

| Variable | Default | Effect |
| --- | --- | --- |
| `OMNIPLOT_IR_ENABLED` | unset | When `1`, the pipeline writes a `GeometryIR` artifact alongside the SVG into `ir_artifact_cache`. Write-only today; the consumer ships next. |

## See also

- [`docs/getting_started.md`](../docs/getting_started.md)
- [`docs/deployment.md`](../docs/deployment.md)
- [Install on a Raspberry Pi](Install-on-a-Raspberry-Pi.md)
