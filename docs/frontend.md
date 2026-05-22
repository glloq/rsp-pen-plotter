# Frontend

The UI is a Vue 3 + TypeScript (strict) single-page app built with Vite, styled
with Tailwind, and using Pinia for state and vue-i18n for translations. It talks
to the backend over a typed axios client and a WebSocket for live plotter
progress.

## Components (`src/components/`)

| Component | Responsibility |
| --- | --- |
| `FileUpload.vue` | Choose a file and profile/preset; POST `/upload` |
| `SvgPreview.vue` | Pan/zoom SVG viewer with per-layer visibility toggles |
| `LayerPanel.vue` | Drag-and-drop layer list + optimize/generate actions and metrics |
| `LayerCard.vue` | One layer: visibility, pen slot, speed, simplify, optimize |
| `GcodePreview.vue` | Generated G-code text + download |
| `Simulator.vue` | Animated playback of the program on a canvas |
| `JogControls.vue` | Manual jog / home controls |
| `PlotterPanel.vue` | Connect, send job, pause/resume/abort, live progress |
| `JobHistory.vue` | Past jobs from the history endpoint |

Components use `<script setup>` with typed props throughout. The G-code
simulation parser lives in `src/lib/gcode.ts` (unit-tested in
`src/lib/gcode.test.ts`).

## Stores (`src/stores/`)

- **`job.ts`** — the upload → layers → optimize → generate lifecycle: holds the
  pivot SVG, layer list and visibility, selected profile, and computed
  statistics (total length, estimated duration). Layer mutations and the
  optimize/generate calls are store actions.
- **`plotter.ts`** — connection parameters, streaming `status`, a `progress`
  computed, and the WebSocket. The socket reconnects while a device is believed
  attached; malformed frames are ignored rather than throwing inside the
  handler.

## API client (`src/api/client.ts`)

A typed axios instance whose base URL comes from `VITE_API_URL` (default
`http://localhost:8000`), plus a `websocketUrl()` helper for `/ws/plotter`. All
backend response shapes are mirrored as TypeScript types (e.g. `LayerInfo`,
`PlotterStatus`).

## Internationalization (`src/locales/`)

`en.json` and `fr.json` hold parallel message trees consumed via `useI18n()`.
Keys must stay in sync across both files; user-facing strings go through `t()`
rather than being hardcoded.

## SVG safety

`SvgPreview.vue` renders uploaded/converted SVG into the DOM, so it sanitizes
the markup with DOMPurify (`USE_PROFILES: { svg: true, svgFilters: true }`)
before assigning `innerHTML`. The backend additionally hardens SVG in
`core/sanitize.py` (stripping scripts, event handlers, and `javascript:` URLs),
so sanitization happens on both ends.
