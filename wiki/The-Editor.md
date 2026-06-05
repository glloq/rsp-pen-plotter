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
*Generate* will commit. It never reaches algorithm options like
`min_distance_mm` or `eps_steps`: it picks sensible defaults and surfaces
two or three sliders per algorithm.

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

Use Compare for cross-hatch vs. stippling on the same portrait, or
different `min_distance_mm` for stippling density.

## Saved presets

Save the entire layer × algorithm × options vector with **Save as
preset**. Presets appear in `GET /presets` (and the dropdown in either
editor) so the same look applies to a new file in one click.

Presets are versioned by content hash, so updating one doesn't
retroactively change past plots.

## Shortcuts

- **⌘/Ctrl + Enter** — next step (Assistant) / Generate (Review step)
- **⌘/Ctrl + Backspace** — previous step
- **⌘/Ctrl + M** — toggle Assistant ⇆ Expert
- **Esc** — close editor (asks to confirm if you have unsaved tweaks)

Full list: [`docs/shortcuts.md`](../docs/shortcuts.md).
