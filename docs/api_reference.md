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
The registered raster-art algorithms with their option schemas, family
(`fill` / `lines` / `mono_stroke`) and complexity hint. Used by the bitmap
editor UI to lay out cards and pre-warn on slow previews. See
[`converters.md`](converters.md) for the full algorithm table.

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

### `POST /plotter/goto`
Absolute move to `{ "x_mm", "y_mm", "profile_name" }`. Same error codes as
`/jog`.

## Files library

The library is the persistent home of every uploaded file. Uploads add to it,
the queue and placements reference it by `file_id`.

| Method & path | Notes |
| --- | --- |
| `POST /files` | Upload a file to the library, returns its record |
| `GET /files` | Paginated list with filters (kind, folder, search) |
| `GET /files/{file_id}` | A single file record |
| `GET /files/{file_id}/original` | Download the original bytes |
| `GET /files/{file_id}/preview-image` | A cached PNG thumbnail |
| `GET /files/by-hash/{sha256}` | Lookup by content hash (dedup) |
| `GET /files/folders` | List of distinct folder labels |
| `GET /files/integrity` | Library integrity scan (orphaned hashes, missing previews) |
| `PATCH /files/{file_id}` | Rename, move folder, edit tags |
| `DELETE /files/{file_id}` | Delete; placement references are cleaned up |

## Queue

All queue endpoints honour the optional `OMNIPLOT_API_KEY`. `POST /queue`
honours an `Idempotency-Key` header for safe automation retries.

| Method & path | Notes |
| --- | --- |
| `GET /queue` | List active + pending + recent finished runs |
| `GET /queue/{run_id}` | A single run with checkpoint and pen-change state |
| `POST /queue` | Enqueue a job from a generated G-code blob + plan |
| `POST /queue/{run_id}/pause` | Soft-pause (firmware-portable) |
| `POST /queue/{run_id}/resume` | Resume from checkpoint |
| `POST /queue/{run_id}/cancel` | Abort and clean up |
| `POST /queue/{run_id}/confirm-swap` | Operator confirms a guided pen change |

## Preflight, preview, rerender, optimize

| Method & path | Notes |
| --- | --- |
| `POST /preflight` | Drawing/travel length, time estimate, pen-change count for a plan |
| `POST /preflight/svg` | Same, but takes a raw SVG (lighter, used by Compare) |
| `POST /preview` | Synchronous per-layer raster preview |
| `GET /preview/stream` | SSE preview pipeline for progressive feedback |
| `POST /preview-text` | Hershey typography preview for a Markdown / TXT snippet |
| `POST /rerender` | Re-renders a placement with updated layer settings |
| `POST /optimize` | vpype linemerge → linesimplify → linesort per layer |
| `POST /document/analyze` | Multi-page PDF / Office document analysis |

## Plans, policy, available colours

| Method & path | Notes |
| --- | --- |
| `GET /plans/{plan_hash}` | Resolved plan for a given content + settings hash |
| `POST /policy/resolve` | Wizard recommendation given source kind + goal |
| `GET /available-colors` | Pen colours available on the active machine |

## Macros

| Method & path | Notes |
| --- | --- |
| `GET /macros` | List user macros |
| `POST /macros` | Create / update a macro |
| `DELETE /macros/{name}` | Delete a macro |
| `POST /macros/{name}/run` | Execute on the connected plotter (`OMNIPLOT_API_KEY` required) |

## Manifests, presets, fonts, settings

| Method & path | Notes |
| --- | --- |
| `GET /manifests` | All algorithm + UI manifests with a single hash |
| `GET /manifests/{domain}` | One manifest by domain (e.g. `algorithms`) |
| `GET /presets` | Built-in parameter presets |
| `GET /fonts` | Bundled Hershey single-stroke font names |
| `GET /settings/palette-source` | Where pen palettes are loaded from |
| `PUT /settings/palette-source` | Override the source |

## Audit

| Method & path | Notes |
| --- | --- |
| `GET /audit` | Append-only log of sensitive actions (connect, run, queue, macro) |

## System

| Method & path | Notes |
| --- | --- |
| `GET /version` | Running version + git revision |
| `GET /check-update` | Behind / ahead of `origin/main`, advisory only |
| `POST /system/update` | Pull + rebuild + restart (disabled when `OMNIPLOT_DISABLE_UPDATE=1`) |

## SLO

| Method & path | Notes |
| --- | --- |
| `GET /slo/budgets` | Current SLO budgets and recent samples |
| `POST /slo/evaluate` | Force an immediate budget evaluation |
