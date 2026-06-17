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
| `GET /plotter/commands` | — | Recent G-code lines sent to the device, for the Plotter-tab command history |
| `POST /plotter/connect` | `{ "port", "baudrate", "terminator": "cr"\|"lf"\|"crlf" }` | Opens the serial link; `400` if it cannot open |
| `POST /plotter/disconnect` | — | Aborts any job and closes the transport |
| `POST /plotter/jog` | `{ "dx_mm", "dy_mm", "dz_mm", "profile_name" }` | Relative move; `dz_mm` drives a motorised Z axis (defaults to `0`). `404` unknown profile, `409` if a job is active |
| `POST /plotter/home` | query `profile_name`, optional `axis` (`X`/`Y`/`Z`) | Homes the machine — all axes, or a single `axis`; `404`/`409` as above, `422` on an invalid axis |
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

## G-code file library

Saved G-code programs the operator can re-print on demand. A saved program is
just stored text — saving never starts a print; `POST /gcode-files/{id}/print`
is the explicit launch (it enqueues the program as a run linked back via
`gcode_file_id` and wakes the queue worker). Programs persist in the SQLite
database (`OMNIPLOT_DB`). Each summary carries `length_mm_by_color` (per-colour
drawn length in mm) so the UI can advance the ink odometer on a re-print.

| Method & path | Notes |
| --- | --- |
| `GET /gcode-files` | List saved programs, newest first — summaries **without** the `gcode` payload |
| `POST /gcode-files` | Save `{ name, profile_name, gcode, length_mm_by_color? }`; `422` if the program is empty |
| `PATCH /gcode-files/{file_id}` | Rename; `404` if unknown |
| `DELETE /gcode-files/{file_id}` | Delete; `404` if unknown |
| `POST /gcode-files/{file_id}/print` | Enqueue the saved program as a run and wake the worker; `404` if the file or its profile is unknown |

These endpoints honour the optional `OMNIPLOT_API_KEY`.

## Timelapse

Capture frames from a configured camera while a print runs, then assemble them
into an H.264 MP4 with ffmpeg. Only one recording runs at a time. The frontend
passes the camera's `stream_url` (cameras are configured client-side, in the
Settings modal); the backend grabs JPEG frames from either a snapshot endpoint
(`image/jpeg`) or an MJPEG stream (`multipart/x-mixed-replace`). Recordings are
stored under `OMNIPLOT_TIMELAPSE_DIR`. Requires `ffmpeg` on `PATH`.

| Method & path | Notes |
| --- | --- |
| `GET /timelapse/status` | Live recorder state (`recording`, `session_id`, `label`, `frame_count`, `interval_seconds`, `fps`, `started_at`, `error`) |
| `POST /timelapse/start` | Begin capturing `{ stream_url, interval_seconds, fps, label? }`; `422` on a non-`http(s)` URL, `409` if already recording |
| `POST /timelapse/stop` | Stop and assemble the MP4; returns a `TimelapseSummary`; `409` if not recording |
| `GET /timelapse` | List saved recordings, newest first (`TimelapseSummary[]`) |
| `GET /timelapse/{id}/video` | Download the MP4 (`video/mp4`); `404` if no video |
| `DELETE /timelapse/{id}` | Delete a recording; `404` if unknown or still active |

Constraints (enforced on both ends): interval `0.5`–`3600 s` (default `5`),
FPS `1`–`60` (default `24`), frames capped at `8 MB` each and `100 000` total.

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
