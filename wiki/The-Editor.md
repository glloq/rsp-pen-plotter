# The editor

OmniPlot has **two** editor surfaces that share the same underlying
model. You choose between them from the header toggle (or the
"Ouvrir l'éditeur complet" button in the assisted footer) — *Assistant*
(single-screen wizard, three clicks max) or *Expert* (rich per-layer
panel + preset save/load). The switch is mid-session safe: the draft
survives, only the surface changes.

> **Why two?** Beginners get lost in a 30-control panel; experts get
> annoyed by a wizard that hides knobs. Sharing the model means an expert
> can save a preset and a beginner can apply it without ever opening Expert
> mode.

## Common model

Both editors edit a **placement** — a `(library file, position on sheet,
layers, per-layer settings, variant)` tuple. The shared keys are:

- **algorithm** per layer (`stippling`, `crosshatch`, `flowfield`, …)
- **options** per layer (algorithm-specific, e.g. `density`, `angle_deg`)
- **target pen slot** per layer
- **drawing speed** per layer
- **simplification tolerance** per layer (vpype `linesimplify`)
- **optimise** per layer (vpype `linemerge → linesort`)
- **multi-pass stack** per layer (e.g. dense crosshatch = pass-1 + pass-2
  offset by 45°)

Switching surface preserves all of the above.

## Print styles — the primary selection model

Day to day you rarely pick a raw algorithm: you pick a **print style** — a
named bundle of algorithm + options (and, for master styles, the
segmentation too). All 136 styles live in one registry,
`frontend/src/data/printRegistry.ts`, split by **scope**:

- **Master styles** (`scope: 'master'`, 85 entries) own the whole result:
  segmentation method, default algorithm, and a per-band / per-cluster
  recipe applied to every produced layer. They come in two families,
  switched by the colour-mode toggle on the **Style tab**:
  - 34 **tonal (monochrome)** masters — Pencil, Halftone shaded,
    Stippling shaded, Engraving, Outline, Etch burin, String thread,
    Coral growth, … driven by luminance-bands / threshold / Otsu
    segmentation. Pencil is the default.
  - 51 **multicolour** masters (ids prefixed `color-*`) — driven by
    k-means / fixed-palette segmentation, with a per-colour-cluster
    recipe. Flat aplats (`color-flat`) is the default.
- **Layer styles** (`scope: 'layer'`, 51 entries) are per-layer presets —
  algorithm + options for a single layer or pass, with no segmentation
  responsibility.

How it surfaces in the UI:

- The **Style tab** carries the master-style gallery
  (`MasterStylePicker`): one card per style with thumbnail, label and
  one-line description, filtered to the active colour mode. Selecting a
  card commits the style id into the draft and re-renders. A **Custom**
  pill appears when you've tweaked segmentation or algorithm knobs past
  the preset's defaults, so the highlighted tile never lies about what's
  actually rendered.
- Each **layer card** carries the per-layer picker (`PrintStylePicker`): a
  curated short-list of general-purpose styles up front, the long tail
  behind a *show all* toggle, and a *Default* tile that clears the
  override so the layer falls back to what the master style baked in. The
  picker hides while a multi-pass stack is active — you edit one source of
  truth at a time.

Saved placements from before the registry merge keep working: legacy
master ids are mapped to the renamed registry entries on rehydration.

## Assistant — the six-step wizard

For: a fresh print, a learner, a quick result.

1. **Source** — what was uploaded. Pre-filled from the file's MIME.
2. **Goal** — what you want out (line art / shaded portrait / poster /
   technical drawing / typography). Drives the recommendation engine.
3. **Render** — algorithm choice + defaults. The wizard pre-selects the
   recommended one based on (Source, Goal). You can override.
4. **Colours** — how many pens to use; the wizard splits the source
   accordingly (k-means for bitmaps, layer-/colour-based for vectors).
5. **Layers** — confirm which layers print and which sit out.
6. **Review** — pre-flight summary (drawing length, travel, time, swaps,
   bounds) and the *Generate* button.

The wizard re-renders the placement on every step so you always see what
*Generate* will commit. It never reaches the long tail of algorithm
options like stippling's `dot_radius_px` or flowfield's `step_px`: it
picks sensible defaults and surfaces two or three sliders per algorithm.

Need a knob the wizard hides? Click **Switch to Expert mode** in the
footer.

## Expert — the rich per-layer panel

For: tuning a known-good preset, doing something the wizard can't, building
a multi-pass result.

The Expert panel surfaces:

- the full algorithm grid grouped by family (*fill* / *lines* /
  *mono_stroke*), with the per-algorithm option schema in a flyout
- per-layer pen slot, drawing speed, simplification tolerance, optimise
  toggle, opacity slider (preview-only), visibility
- multi-pass stack editor: build a chain of `(algorithm, options)` that
  apply to the same layer in order, sharing the same pen
- the *Compare* drawer: pick two variants and view them side-by-side with
  per-variant metrics (length, time, swap count)

Expert mode never re-derives layers from the source — what's on screen is
the truth.

## Live preview

Both editors share the same preview pipeline:

- a debounced `/rerender` call on every change
- progressive feedback through SSE on `/preview/stream` for slow
  algorithms (TSP, Voronoi stippling, flow field, low-poly)
- a per-algorithm complexity hint that pre-warns you before slow previews
- preview cost EMA — the UI learns how long *your* Pi takes and adjusts
  the warning threshold

When the preview can't keep up (you cycle algorithms faster than they
render) the previous successful render stays on screen; the new one
arrives when ready.

## Variants & Compare

Each placement keeps up to two variants. The *Compare* drawer (header
button or the *Compare* link in either editor footer) opens a side-by-side
view with:

- both renders rendered against the same sheet
- a metrics row per variant: drawing length, travel, estimated time, swap
  count
- a *Pick A* / *Pick B* button that commits the choice and closes the
  drawer

Use Compare for cross-hatch vs. stippling on the same portrait, or two
different stippling `density` settings.

## Saved presets

The Expert panel's *Presets* row carries built-in styles ("Halftone",
"Stippling", "Fine line", "Posterized") plus everything you've saved
yourself. Click a chip to apply it to every layer of the current
placement (a fresh `/rerender` follows immediately). Use **Save as
preset** to snapshot the active placement's algorithm + options bundle
so the same look applies to a new file in one click.

Built-in presets are read-only; user-saved presets carry a small `×`
button to delete them. The store lives in JSON next to the SQLite DB
(`data/user_presets.json`) and is capped at 64 entries.

## Shortcuts

- **⌘/Ctrl + Enter** — next step (Assistant) / Generate (Review step)
- **⌘/Ctrl + Backspace** — previous step
- **⌘/Ctrl + M** — toggle Assistant ⇆ Expert
- **Esc** — close editor (asks to confirm if you have unsaved tweaks)

Outside the editor, queue resume is plain **R** (no modifier — Ctrl/Cmd+R
stays the browser reload).

Full list: [`docs/shortcuts.md`](../docs/shortcuts.md).
