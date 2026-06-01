# Pen magazine

The pen magazine is the rack / carousel that holds your pens. OmniPlot's
model: an ordered list of **slots**, each carrying one pen. The active
machine profile declares the slot count.

## Anatomy

- **slot_count** — how many physical positions exist
- **slots** — array of `{ id, name, colour }`, one per slot
- **active_slot** — which slot is currently loaded in the carriage
  (state, not config)

A typical 4-pen magazine:

```yaml
pens:
  slot_count: 4
  slots:
    - { id: 1, name: "Sakura Micron 005 (black)", colour: "#111" }
    - { id: 2, name: "Sakura Micron 005 (sepia)", colour: "#5b3a1a" }
    - { id: 3, name: "Stabilo 88 (red)",         colour: "#d2412c" }
    - { id: 4, name: "Stabilo 88 (blue)",        colour: "#1f4cd2" }
```

## Pen changes

A plot using N pens implies N − 1 swaps (or more, if the toolpath
optimiser decides revisits are cheaper than backtracking). Two modes:

- **Automatic** — the machine has a real carousel; the firmware /
  G-code performs the swap. The queue does nothing — it streams across.
- **Manual (default)** — the queue inserts a software-driven pause and
  prompts the operator with a *Swap to slot N* modal. Confirm, swap the
  pen physically, click *Continue*.

The downloaded G-code still contains `M0` so that running it through
another sender behaves portably.

## Pen-swap planner

The toolpath optimiser reorders layers to minimise swap count. You see
its effect in pre-flight (the *Pen changes* counter). Trade-off:

- minimising swaps can lead to more pen-up travel
- minimising travel can lead to more swaps

The default heuristic prioritises swap count, on the assumption that a
swap is slower than even a long travel. Override per-layer with the
*pin layer order* toggle in Expert mode.

## Missing slot detection

If you assign a layer to slot 5 on a 4-slot magazine, pre-flight blocks
*Generate*. You'll see a red banner: *"Layer 'water' points to slot 5
but the magazine only has 4 slots."* Reassign or grow the magazine.

## Calibration

Different pens need different servo depths or different XY offsets:

- per-slot pen-up / pen-down command override → [Per-slot calibration](Per-Slot-Calibration.md)
- per-slot XY offset (if your carousel doesn't centre pens precisely) →
  set in the profile editor; applied as a global translate during
  G-code generation for that pen's strokes

## Colours and palettes

The pen *colour* attribute is advisory — the editor uses it to colour
the layer chips, the preview SVG and the *Colours* step. It doesn't
affect what the plotter draws. Pick honest colours so previews tell
the truth.

A *palette source* setting (Settings → Settings → palette source) lets
you point OmniPlot at a CSV list of named colours (Stabilo, Staedtler,
Sakura, …); the profile editor will offer those as autocompletes.

## See also

- [Machine profiles](Machine-Profiles.md)
- [Per-slot calibration](Per-Slot-Calibration.md)
- [`docs/tool_change_mechanisms.md`](../docs/tool_change_mechanisms.md)
