# Editor UI Audit (2026-06)

Scope: the edit modal and everything it renders —
`components/v2/EditModalV2.vue`, `EditPreviewPane.vue`, `StyleCustomizer.vue`,
`LayerInspector.vue`, and the whole `components/edit/**` tree (tabs, cards,
layer/pass stack, shared widgets). Goal: identify why the editor looks
"rougher" than the rest of the app and define a concrete path to visual
consistency.

## Reference: the app's design system

The rest of the app is a single, coherent system:

- **Tailwind utilities only**, almost no scoped CSS, no `dark:` variants —
  the app is *always dark* (`App.vue` root: `bg-slate-900 text-slate-100`).
- **Palette**: slate for surfaces/borders/text (`bg-slate-800` panels,
  `border-slate-700`, `text-slate-300/400/500`), with functional accents:
  emerald = primary/success, amber = warning, red = danger, sky = info,
  usually as `*-950/40`-style translucent fills with `*-700` borders.
- **Modals**: overlay `fixed inset-0 z-40 bg-black/60` (or
  `bg-slate-950/80 backdrop-blur-sm`), container
  `rounded-xl border border-slate-700 bg-slate-900 shadow-2xl`
  (`PlotterSettingsModal.vue:148`), header `border-b border-slate-700 px-4 py-3`.
- **Buttons**: secondary
  `rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700`;
  CTA `rounded bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500`;
  danger `bg-red-700 hover:bg-red-600`.
- **Inputs/selects**: `rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100`.
- **Section titles**: `text-xs uppercase tracking-wider text-slate-500`.
- **Type/spacing scale**: `text-sm` body, `text-xs`/`text-[11px]` controls,
  `font-mono` for measurements; `gap-2`/`space-y-2`, `p-3` cards.

## Verdict

The editor is split across **two unrelated design languages**:

1. The **expert-mode internals** (`components/edit/**`: `EditTabs`, the five
   tabs, all image/style/color cards, `LayerPassStack`, `LayerBulkBar`,
   `AssignedColorPicker`, `PrintStylePicker`, …) are already pure Tailwind,
   dark slate, emerald-accented — i.e. **already conform** to the app system.
2. The **modal shell and assisted mode** (`EditModalV2`, `EditPreviewPane`,
   `StyleCustomizer`, `LayerInspector`) are a **light theme** built from
   ~1 200 lines of scoped CSS with hardcoded hex values — white surfaces,
   `#1e293b` text, a `#1f6feb` blue accent that exists nowhere else in the
   main app.

The result on screen: a white card floats over the dark app, and when expert
mode opens, dark slate panels are nested *inside* the white card
(`.modal-v2__expert` sets `background: #0f172a` at `EditModalV2.vue:1364`).
This shell mismatch — not the controls themselves — is what makes the editor
feel unpolished.

## Findings

### F1 — Light shell on a dark app (critical)

- `EditModalV2.vue:1301-1315`: `.modal-v2 { background: white; color: #1e293b; }`
  vs. every other modal in the app (`ConfirmDialog`, `PlotterSettingsModal`,
  `SettingsDrawer`) which uses `bg-slate-800/900` + `border-slate-700`.
- Header divider `border-bottom: 1px solid #e2e8f0` (`:1388`), light chips
  (`is-ok` → `#ecfdf5`, `is-warn` → `#fff7ed`, `is-info` → `#f8fafc`,
  `:1420-1434`), light ghost buttons (`:1453-1461`) — all light-mode tokens.
- `EditPreviewPane.vue` chrome (zoom buttons, mode toggle, split handle,
  captions) is also light: `background: white` (`:1018`), `#f1f5f9`,
  `#cbd5e1` borders. (The *sheet* preview itself legitimately stays white —
  it represents paper.)

### F2 — Competing accent colors

- The v2 shell uses **`#1f6feb` blue** as primary (~15 occurrences across
  `EditModalV2`, `EditPreviewPane`, `StyleCustomizer`); the app's primary is
  **emerald** (`bg-emerald-600` CTAs, `border-emerald-600 bg-emerald-950/40`
  active states — exactly what `MasterStylePicker`/`EditTabs` already use).
  Two different "selected/primary" colors coexist inside one modal.

### F3 — Off-palette grays in LayerInspector

- `LayerInspector.vue` uses its own neutral set (`#e0e0e0`, `#f0f0f0`,
  `#555`, `#999`, `rgba(0,0,0,0.1)`) plus `#2e7d32`/`#b71c1c` for states —
  matching neither slate nor the emerald/red functional accents.

### F4 — Two styling mechanisms, duplicated primitives

- Scoped BEM CSS (`.modal-v2__*`, ~500 lines) re-implements buttons, chips,
  fieldsets and focus rings that already exist as Tailwind patterns ten
  lines away in `components/edit/**`. Every future tweak must be done twice.

### F5 — No shared scale (typography, radius, spacing)

- Font sizes in the shell: `0.6 / 0.7 / 0.72 / 0.8 / 0.85 / 0.9 / 1 / 1.05 /
  1.5 rem` (9+ values) vs. the app's compact `text-sm` / `text-xs` /
  `text-[11px]` scale.
- Border radii: `2px / 4px / 6px / 8px / 999px` vs. the app's
  `rounded` / `rounded-lg` (+ `rounded-xl` for modals, `rounded-full` pills).
- Spacing: raw `0.18rem`, `0.3rem`, `0.35rem`, `0.4rem`, `0.6rem`, `0.65rem`
  vs. the Tailwind `gap-1/2/3`, `p-2/3` scale.

### F6 — Rough edges

- Unstyled native inputs: bare `<input type="range">`
  (`BasicAdjustmentsCard`), `<input type="number">` without focus states
  (`PostProcessCard`), inconsistent checkbox focus rings.
- Missing `:hover`/`:focus-visible` on ink swatches and layer-visibility
  toggles in `EditModalV2` (`:1038-1064`).
- Magic numbers: `14px` split handle, `2rem` grip, `calc(92vh - 9rem)`
  sticky clamp, `min(98vw, 1280px)` width — acceptable individually but
  undocumented as a system.

### Scope note

The same light/`#1f6feb` language also lives in other v2 screens
(`WorkshopMode`, `MagazineView`, `CapabilityWizard`, `RunTimeline`,
`RunActionsPanel`, `PresetPanel`). They are outside this audit's scope but
should eventually follow the same migration so the fix doesn't reintroduce
a seam elsewhere.

## Recommended plan (priority order)

**P1 — Re-skin the modal shell to the app's dark modal pattern.**
`EditModalV2.vue`: overlay → `fixed inset-0 z-40 bg-black/60`; container →
`rounded-xl border border-slate-700 bg-slate-900 shadow-2xl text-slate-100`;
header → `border-b border-slate-700`; footer buttons → app secondary/CTA
patterns (emerald CTA replaces `#1f6feb`); header chips → translucent
functional fills (`border-emerald-700 bg-emerald-950/40 text-emerald-200`,
amber/sky equivalents). This single step removes the light-card-on-dark-app
clash and the dark-inside-light nesting.

**P2 — Darken the preview chrome, keep the paper white.**
`EditPreviewPane.vue`: zoom/mode/split controls → app button + slate tokens;
sheet outline/caption → `border-slate-600`/`text-slate-400`; the rendered
sheet keeps its white background (it depicts paper) — the dark surround will
actually increase its contrast, like `SheetCanvas` in the main view.

**P3 — Converge `StyleCustomizer` and `LayerInspector`.**
Replace scoped light CSS with the Tailwind card pattern
(`rounded-lg border border-slate-700 bg-slate-800 p-3`); selected state →
`border-emerald-600 bg-emerald-950/40 text-emerald-200` (identical to
`MasterStylePicker`); drop the off-palette grays and `#2e7d32`/`#b71c1c`
in favor of emerald/red families.

**P4 — Normalize tokens across the editor.**
Typography down to `text-sm` / `text-xs` / `text-[11px]`; radii to
`rounded` / `rounded-lg` / `rounded-full`; spacing to the Tailwind scale;
`accent-emerald-500` + a standard `focus-visible:outline` treatment on all
native inputs (range, number, checkbox); add the missing hover/focus states
listed in F6.

**P5 (optional) — Extract the 3–4 most-repeated primitives.**
Either `@layer components` classes in `style.css` (e.g. `.btn`, `.btn-cta`,
`.card`, `.chip`) or tiny Vue primitives, so the shell and the expert cards
stop duplicating class strings verbatim. Low urgency; P1–P4 already deliver
the visual consistency.

Expected effort: P1+P2 are the bulk (the two big scoped-CSS files);
P3–P4 are mechanical. No behavioral/markup-structure changes are required —
this is a styling migration, so existing component tests should be
unaffected; visual review via the e2e/screenshot flow is the main check.

## Status: applied (2026-06)

P1–P5 are implemented in the same branch as this audit:

- **P1** `EditModalV2.vue` — dark slate-900 shell, slate-700 borders,
  emerald CTA/active states, translucent functional chips, dark tour
  overlay. The `.modal-v2__expert` drawer lost its own surface (cards
  sit directly on the modal background, as in the main view).
- **P2** `EditPreviewPane.vue` — dark checkerboard + chrome (zoom, mode
  toggle, overlay, split handle in emerald); the sheet is now solid
  white so the plot reads as ink on paper.
- **P3** `StyleCustomizer.vue`, `LayerInspector.vue` — converted to the
  slate/emerald system; off-palette grays and `#2e7d32`/`#b71c1c`
  removed. `SheetPicker.vue` (mounted under the preview) converted too;
  `PresetPanel.vue` accents aligned (`#1f6feb`/`#1e3a8a` → emerald).
- **P4** — type scale reduced to 1rem / 0.875 / 0.75 / 0.6875 / 0.625rem;
  radii to 4 / 8 / 12px + pills; all focus rings standardized on
  emerald; native range/checkbox/radio inputs get `accent-color`
  emerald via an `@layer base` rule in `style.css`.
- **P5** — `.btn`, `.btn-cta`, `.card`, `.chip` primitives added in
  `@layer components` (`style.css`); `.card` adopted across the 11
  exact-duplicate card strings in `components/edit/**`. Adoption
  elsewhere is incremental.

Out of scope, still light-themed: `WorkshopMode`, `MagazineView`,
`CapabilityWizard`, `RunTimeline`, `RunActionsPanel`, `PipelineInspector`.

**Follow-up (same branch):** the remaining light/off-palette surfaces were
migrated too — `WorkshopMode`, `MagazineView`, `CapabilityWizard` (including
its previously unstyled native inputs and footer buttons), `RunTimeline`,
`RunActionsPanel`, `PipelineInspector`, plus the shared
`AssistantModeToggle` (rendered in the edit-modal header) and
`ManifestFallbackBanner`; `PerfOverlay`'s neutral grays were aligned to
slate. No light-themed component remains; the only intentional white
surface left is the paper sheet in `EditPreviewPane`.
