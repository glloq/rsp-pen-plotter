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

## Edit modal (V2 only, since the v0.2 migration)

`EditModalV2.vue` is the sole editor surface (the legacy `EditModal.vue`
and its "Open V1 editor" escape hatch are gone). It runs in **two UX
modes**, toggled by `AssistantModeToggle` (backed by the `uiMode` store):

- **Assisted** (default) — the guided single screen: an intent picker
  (fast / balanced / quality), a palette source toggle (machine pens vs.
  free inventory), an optional beginner style stack (`StyleCustomizer`),
  the sheet picker (`SheetPicker`), the live preview, the ink chips, and
  the four-chip preflight checklist. Zero clicks to a first result.
- **Expert** — restores the V1 source cards behind the tab strip
  (`EditTabs`): `ImageTab` (preprocess), `SvgTab`, `StyleTab` (master
  style), `TextTab` (typography), and `LayersSection` (per-layer
  algorithm / passes / colour). The **Appliquer** button commits the
  draft back to the placement via `useFileManager.uploadSelected`. These
  surfaces are **lazy-loaded** (`defineAsyncComponent`) so the assisted
  open stays light — they fetch only when the operator flips to expert.

So per-layer fine controls **are** available inside the modal (in expert
mode), in addition to `LayerCard` in the main canvas, which still offers
the same algorithm / passes / colour controls outside the modal.

### Modal composables (`src/composables/`)

The modal is being refactored from a single 2300-line SFC toward a thin
orchestrator over focused, unit-tested composables:

- **`useEditorPreviewPipeline`** — the single preview scheduler. One
  `schedule(level)` entry point with invalidation levels
  (`render-only` / `segment-and-render` / `resolve-and-segment`), one
  debounce timer, one `AbortController`. Bursts collapse to one flush at
  the strongest level; owns `decision` / `resolving` / `renderedSvg` /
  `previewLoading` / `previewError`.
- **`useEditorPaletteSegmentation`** — `effectivePool` plus the
  `kmeans_lab` + `ink_pool` re-upload that keeps the segmentation in step
  with the operator's pool.
- **`useEditorConfirmation`** — the race-safe Generate path: in expert
  mode it awaits the dirty-draft upload before emitting `confirm`, so the
  parent never generates from the pre-apply SVG.
- **`useEditorPreflight`** — drawing estimates, ink compatibility, and the
  preflight checklist.
- **`useEditorOnboarding`** — the first-run welcome tour + preamble card
  (localStorage-backed).
- **`lib/errorMessage`** — shared `unknown → string` normaliser.

### Compare / styles

The standalone Compare drawer (`v2/CompareView`) covers two variants;
V1's multi-style grid (`MasterStylePicker` thumbnails) is not ported.

## SVG safety

`SvgPreview.vue` renders uploaded/converted SVG into the DOM, so it sanitizes
the markup with DOMPurify (`USE_PROFILES: { svg: true, svgFilters: true }`)
before assigning `innerHTML`. The backend additionally hardens SVG in
`core/sanitize.py` (stripping scripts, event handlers, and `javascript:` URLs),
so sanitization happens on both ends.
