# API Reference

Base URL defaults to `http://localhost:8000`. All bodies are JSON unless noted.
Models referenced here are defined in `backend/pen_plotter/models.py` and the
per-router request/response classes. The complete, generated route list lives
in `backend/openapi.json`.

**Cross-origin guard (open mode).** When `OMNIPLOT_API_KEY` is *unset*, a
middleware rejects state-changing requests (anything but `GET`/`HEAD`/`OPTIONS`)
whose `Origin` header matches neither the request `Host` nor the
`OMNIPLOT_CORS_ORIGINS` allow-list — they get a `403` (CSRF / DNS-rebinding
protection). Requests without an `Origin` header (curl, scripts, SDKs) are
unaffected, and locked mode relies on the API key instead.

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

### `POST /profiles`
Body is a `MachineProfile` JSON object; validates and stores it under
`OMNIPLOT_PROFILES_DIR`.

### `POST /profiles/import`
Body is a YAML profile; validates against the schema and stores it under
`OMNIPLOT_PROFILES_DIR`. Invalid YAML/schema → `400`.

### `DELETE /profiles/{name}`
Removes a user-imported profile. Bundled profiles cannot be deleted.

## Presets, fonts, algorithms

### `GET /presets`
Built-in + user parameter presets (e.g. fine line, dense hatching, stippling).

### `POST /presets`
Create a user preset (`201`). Name validated, store capped.

### `DELETE /presets/{name}`
Delete a user preset (`204`). Built-ins cannot be removed.

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
| `POST /plotter/abort` | — | Abort the running job (waits for the current `ok`) |
| `POST /plotter/emergency_stop` | optional query `profile_name` | Real-time stop, preempting any in-flight move: writes the dialect's emergency payload (GRBL `0x18`, Marlin `M112`, EBB `ES`) straight to the line and cancels the stream |

### `WS /ws/plotter`
On connect, the server sends the current status, then pushes a status object on
every streaming progress update:
`{ "connected", "total", "sent", "acked", "state" }`. The client closes the
socket to unsubscribe; it reconnects automatically while it believes a device is
attached.

### `POST /plotter/goto`
Absolute move to `{ "x_mm", "y_mm", "profile_name" }`. Same error codes as
`/jog`.

## Tip-offset calibration (camera)

Measure per-pen XY offsets at a dedicated camera station (ADR 0005, phase 2).
The station config (`camera_url`, `mm_per_pixel`, `reference_slot`, …) lives on
the profile and is passed inline. Measurement is **relative**: measure the
reference pen first, then each other pen reports its offset versus the
reference. The offset is persisted onto the slot via the normal `POST
/profiles` path (the magazine editor does this on Accept).

| Endpoint | Body | Purpose |
| --- | --- | --- |
| `POST /plotter/tip-calibration/measure` | `{ "slot", "camera_url", "mm_per_pixel", "reference_slot", "dark_threshold"?, "roi"?, "fetch_pen"?, "move_to_station"?, "station_position"?, "profile_name"? }` | Grab one frame, locate the tip, return `{ found, tip_px, confidence, reference_measured, offset_mm, … }`. Optional motion first (order: fetch → travel → grab): `fetch_pen` loads the slot's pen via a tool-change swap; `move_to_station` then travels to `station_position`. Both need a connected plotter + `profile_name` (`409` disconnected / manual-swap profile, `422` under-specified). `502` if the camera read fails |
| `GET /plotter/tip-calibration/status` | — | `{ "measured_slots": [...] }` for the current session |
| `POST /plotter/tip-calibration/reset` | — | Forget all measurements (start a fresh run) |

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
honours an `Idempotency-Key` header for safe automation retries: a second
request with the same key returns the existing run (the keys are persisted
with the run — there is no expiry window).

`GET /queue` returns **summaries without the `gcode` payload**
(`PrintRunSummary`: `id`, `name`, `profile_name`, `total_lines`,
`acked_lines`, `state`, `priority`, `error`, `swap_prompt`,
`skipped_layers`, `idempotency_key`, `created_at`, `updated_at`) — the
frontend polls it every few seconds, and serialising the full program per
run made each poll a multi-MB response. Fetch `GET /queue/{run_id}` for
the full row including `gcode`.

| Method & path | Notes |
| --- | --- |
| `GET /queue` | List runs, active first — `PrintRunSummary[]`, no `gcode` |
| `GET /queue/{run_id}` | The full run, including `gcode`, checkpoint and pen-change state |
| `POST /queue` | Enqueue `{ name, profile_name, gcode, priority }`; `404` on unknown profile |
| `POST /queue/{run_id}/pause` | Soft-pause (firmware-portable) |
| `POST /queue/{run_id}/resume` | Resume from checkpoint; also confirms a guided pen swap the run is waiting on |
| `POST /queue/{run_id}/cancel` | Abort and clean up |
| `DELETE /queue/{run_id}` | Remove a run; `409` while it is streaming (cancel first), `404` if unknown |

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
| `GET /available-colors` | The operator's app-wide ink inventory, in display order |
| `POST /available-colors` | Add a colour (`hex` required; duplicates return the existing entry) |
| `PATCH /available-colors/{color_id}` | Edit name, hex, position, stroke width, odometer |
| `DELETE /available-colors/{color_id}` | Remove a colour; `404` if unknown |

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
| `GET /presets` | Built-in + user parameter presets |
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
| `GET /system/version` | Running version + git revision |
| `GET /system/check-update` | Behind / ahead of `origin/main`, advisory only |
| `POST /system/update` | Pull + rebuild + restart (disabled when `OMNIPLOT_DISABLE_UPDATE=1`) |

## SLO

| Method & path | Notes |
| --- | --- |
| `GET /slo/budgets` | Current SLO budgets and recent samples |
| `POST /slo/evaluate` | Force an immediate budget evaluation |
