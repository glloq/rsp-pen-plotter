# Multi-pass plotting

Some looks need more than one stroke per layer. OmniPlot's **multi-pass
stack** lets you chain `(algorithm, options)` pairs that apply to the
same layer in order, sharing the same pen.

## Recipes

### Dense crosshatch (two-direction)

```
Layer 1 — pen 1 (graphite 0.5 mm)
  Pass 1 — crosshatch · angle 0°  · density 60 %
  Pass 2 — crosshatch · angle 90° · density 60 %
```

Result: classic "+45° / −45°" crosshatch but driven from the layer's
tone map. The two passes share the layer's pen so there's no swap
between them.

### Drop-shadow effect

```
Layer 1 (shadow) — pen 1 (light grey)
  Pass 1 — direct · offset (-1, -1) mm
Layer 2 (line art) — pen 2 (black)
  Pass 1 — direct
```

Plot the offset shadow first, then the crisp lines on top.

### Filled outlines

```
Layer 1 — pen 1 (black 0.3 mm)
  Pass 1 — direct (outline)
  Pass 2 — eulerian_hatch · spacing 0.25 mm (fill)
```

Vector logo: outline first, then fill the bodies with tight hatching
using the same pen.

### Reinforced text

```
Layer 1 — pen 1
  Pass 1 — Hershey text
  Pass 2 — Hershey text (same content)
```

Plots the same Hershey text twice — the second pass darkens any glyph
that didn't lay down enough ink the first time. Useful for thirsty
papers or low-flow pens.

## Editor

In **Expert mode**, the layer panel shows the pass stack as a vertical
list with a *+ Add pass* button. Re-order with drag handles, delete
with the × button, expand a pass to edit its options.

In **Assistant mode**, the wizard occasionally recommends a multi-pass
stack (e.g. *Portrait → Editorial* picks crosshatch ×2). You can accept
it or pick a single-pass alternative.

## Cost

Each extra pass roughly doubles the plot time for that layer. Pre-flight
counts every pass in its time estimate; pen-up travel is shared between
passes so it grows sub-linearly.

## Limits

- a single layer caps at 8 passes (a soft cap to prevent runaway editor
  state — bump it in `domain/layer.ts` if you need more)
- passes always share the layer's pen — multi-pass with multiple pens
  means multiple layers
- the optimiser runs **per pass** (not across them), so don't expect a
  pass-2 stroke to start where pass-1 ended

## See also

- [The editor](The-Editor.md)
- [Picking the right algorithm](Picking-the-Right-Algorithm.md)
- [Pen magazine](Pen-Magazine.md)
