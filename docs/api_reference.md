# API Reference

Base URL defaults to `http://localhost:8000`. All bodies are JSON unless noted.
Models referenced here are defined in `backend/pen_plotter/models.py` and the
per-router request/response classes.

## Health

### `GET /health`
Returns `{ "status": "ok", "version": "<package version>" }`.

## Upload & conversion

### `POST /upload`
Multipart form upload. Field `file` (the document) and optional `options` (JSON
string of converter-specific parameters, e.g. bitmap algorithm). The MIME type
selects the converter via the registry; unknown types return `415`. Uploads are
capped at 50 MB (`413` otherwise). Returns the normalized SVG, the detected
layers, and any converter warnings.

### `POST /optimize`
Body: `{ "svg": string, "layers": [{ "layer_id", "optimize", "simplify_tolerance_mm" }] }`.
Runs the vpype `linemerge → linesimplify → linesort` pipeline per layer and
returns the optimized SVG, refreshed `LayerInfo[]`, and before/after `metrics`
(path length, pen-up travel, travel reduction). Invalid SVG returns `400`.

### `POST /generate`
Body: `GenerateRequest` —
`{ "svg", "profile_name", "layers": [{ "layer_id", "target_pen_slot", "drawing_speed_mm_s" }], "scale_mode": "fit"|"actual", "margin_mm" }`.
Routes to native EBB generation when the profile's dialect is `ebb`, otherwise
to template-driven G-code. Returns `{ "gcode", "line_count" }`. Unknown profile
→ `404`; parse/template failure → `400`/`422`.

## Profiles

### `GET /profiles`
List of available machine profiles (bundled + imported).

### `GET /profiles/{name}`
A single `MachineProfile`. Unknown name → `404`.

### `GET /profiles/{name}/export`
The profile serialized as YAML (`text/plain`).

### `POST /profiles/import`
Body is a YAML profile; validates against the schema and stores it under
`OMNIPLOT_PROFILES_DIR`. Invalid YAML/schema → `400`.

## Presets, fonts, algorithms

### `GET /presets`
Built-in parameter presets (e.g. fine line, dense hatching, stippling).

### `GET /fonts`
Names of the bundled Hershey single-stroke fonts.

### `GET /algorithms`
The registered raster-art algorithms (`direct`, `halftone`, `stippling`) with
their option schemas, for the bitmap converter UI.

## Jobs (history)

### `GET /jobs`
Recent jobs from the SQLite history.

### `GET /jobs/{job_id}`
A single job record. Unknown id → `404`.

## Plotter control

All return a `StatusResponse`:
`{ "connected": bool, "total": int, "sent": int, "acked": int, "state": str }`.

| Method & path | Body | Notes |
| --- | --- | --- |
| `GET /plotter/status` | — | Current connection/streaming snapshot |
| `POST /plotter/connect` | `{ "port", "baudrate", "terminator": "cr"\|"lf"\|"crlf" }` | Opens the serial link; `400` if it cannot open |
| `POST /plotter/disconnect` | — | Aborts any job and closes the transport |
| `POST /plotter/jog` | `{ "dx_mm", "dy_mm", "profile_name" }` | Relative move; `404` unknown profile, `409` if a job is active |
| `POST /plotter/home` | query `profile_name` | Homes the machine; `404`/`409` as above |
| `POST /plotter/run` | `{ "gcode" }` | Starts streaming; `409` if a job already runs |
| `POST /plotter/pause` | — | Pause the running job |
| `POST /plotter/resume` | — | Resume a paused job |
| `POST /plotter/abort` | — | Abort the running job |

### `WS /ws/plotter`
On connect, the server sends the current status, then pushes a status object on
every streaming progress update:
`{ "connected", "total", "sent", "acked", "state" }`. The client closes the
socket to unsubscribe; it reconnects automatically while it believes a device is
attached.
