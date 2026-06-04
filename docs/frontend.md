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

`EditModalV2.vue` is the sole editor surface. The legacy V1 modal
(`EditModal.vue`, ~430 LOC) and its 28 V1-exclusive subcomponents
(`edit/tabs/*`, `edit/image/*`, `edit/render/MasterStyleParams*`,
`edit/svg/*`, `edit/colors/*`, `edit/source/*`, `edit/style/*` +
`EditPreviewPane`, `EditTabs`, `VariantsBar`, `BlockMapCard`,
`UploadFooter`, `EmptyPlacementDropzone`, `DetailPicker`,
`LayerCountBadge`, `DualRangeSlider`, etc.) were removed.

### What operators lost vs. V1

The V2 wizard exposes the resolver-recommended algorithm + a small
set of guided overrides; it does **not** yet replicate V1's rich
per-layer surface. Specifically:

- **No per-layer fine controls inside the modal**: choose-algorithm-
  per-layer, multi-pass stack editor, per-layer image adjustments
  (brightness / contrast / levels / filters / transform), per-layer
  segmentation tuning. These were V1's Layers / Image / Style / SVG
  tabs.
- **No master-style explorer**: V1's `MasterStylePicker` thumbnails
  + `MultiColorMasterStyleParams` (1035 LOC) are gone.
- **No "Compare V1 styles" view inside the modal**: the standalone
  Compare drawer (`v2/CompareView`) covers two variants; the V1
  multi-style grid is not ported.

What's still available, just outside the modal:

- **`LayerCard`** in the main canvas keeps per-layer algorithm
  selection (`AlgoParamsForm`), color assignment
  (`AssignedColorPicker`), multi-pass stack (`LayerPassStack`), and
  print-style picker — these components were shared and survived
  the cleanup.
- **Workshop mode** + **Compare drawer** (V2 surfaces) still ship.

### Migration path for operators

1. Pick the file in the Files pane; click **Edit** → the V2 wizard
   opens.
2. For per-layer tweaks beyond what the wizard exposes, close the
   wizard and use the per-layer cards in the right panel
   (`LayerCard` provides the same algorithm / passes / colour
   controls as V1's Layers tab, just outside a modal).

The escape hatch "Open V1 editor" button is gone — V1 is no longer
mounted.

## SVG safety

`SvgPreview.vue` renders uploaded/converted SVG into the DOM, so it sanitizes
the markup with DOMPurify (`USE_PROFILES: { svg: true, svgFilters: true }`)
before assigning `innerHTML`. The backend additionally hardens SVG in
`core/sanitize.py` (stripping scripts, event handlers, and `javascript:` URLs),
so sanitization happens on both ends.
