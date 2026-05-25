# 0001 — Every input format normalizes to a single SVG pivot

- **Status**: accepted
- **Date**: 2024-09 (back-dated; choice predates this ADR file)

## Context

OmniPlot accepts a heterogeneous set of inputs — raster images (PNG / JPG /
TIFF / WebP / HEIC), vector files (SVG / DXF / EPS), documents (PDF / DOCX
/ HTML / Markdown), plain text, and pre-existing G-code. Each format has its
own parsing quirks, its own coordinate conventions, and its own toolpath
implications.

We had three plausible architectures:

1. **Per-format end-to-end pipelines.** Each converter would emit G-code
   directly from its input. Simple to wire up the first time but every
   downstream concern — layer extraction, pen-slot routing, multi-pass
   rendering, simulation, persistence — has to be re-implemented per format.
2. **An internal toolpath IR** (a list of polylines with metadata). Skips the
   SVG step entirely. Solves the duplication problem but commits the project
   to inventing + maintaining its own intermediate format, with no tooling
   support (no Inkscape preview, no SVG diff, no eyeball debugging).
3. **An SVG pivot.** Every converter emits SVG with Inkscape-flavoured
   layer labels (`<g inkscape:label="…">`). Downstream code (layer
   extraction, optimization, simulation, G-code emission) reads only SVG.

## Decision

Adopt option 3 — **a single SVG pivot**.

```
[Bitmap] [Vector] [Document] [G-code raw]
    │       │         │           │
    └───────┴─────┬───┴───────────┘
                  ▼
         Converter (per MIME)             converters/
                  ▼
         Normalized SVG with labelled <g> groups
                  ▼
         Layer extraction                  core/layers.py
                  ▼
         Plan + optimize + render          vpype, core/gcode.py
                  ▼
                G-code
```

Pre-existing G-code uploads bypass the converter chain (there's nothing to
normalize) but still flow through the same plan / preflight / streaming code
paths.

## Consequences

### Positive

- **One layer-extraction implementation.** Every input goes through
  `core/layers.py`'s SVG group walker. Adding a new input MIME means writing
  a converter that emits labelled SVG — nothing else changes downstream.
- **Inspectable intermediate state.** SVGs render in any browser, diff
  cleanly via text tooling, and survive a `vpype` round-trip with their
  labels intact. This is what unlocked the editor's preview pane: tier-2
  rendering is `v-html` of the same SVG the converter emitted.
- **Toolpath tools come for free.** vpype, picosvg, svgpathtools, and friends
  all consume SVG. We didn't have to write our own optimizer.
- **The `PrintPlan` pivot composes cleanly on top.** Each layer in the plan
  references the SVG by file id; resolved plans carry the SVG group label
  identity end-to-end.

### Negative

- **Two intermediate representations for some formats.** A PDF round-trips
  through `pdftocairo` → SVG → toolpaths; the same pixels could in theory
  go PDF → toolpaths directly. We accept the cost for the architectural
  uniformity.
- **Bitmap segmentation is awkward in SVG.** Per-pixel masks become
  per-region `<path>` elements with stroke colours; the bitmap converter
  package (`converters/bitmap/`, L9 split) carries most of the complexity
  to make this conversion fast on a Pi.
- **The SVG MUST be sanitized before we paint it in the browser.** The
  preview pipeline runs every cleaned SVG through DOMPurify with the
  `svg` profile — see `composables/useSheetGeometry.ts`.
- **Vector-source fidelity is bounded by what vpype + the renderer can
  express.** Effects like raster filters, gradients, or complex clip-paths
  can't survive the pipeline; converters flatten them to strokes at the
  ingestion step.

## Alternatives we still reject

A per-format pipeline would let us claim "lossless" passthrough for some
inputs, but the simulator, the layer editor, the rerender cache, and the
generation flow all assume a uniform pivot. Switching now would require
rewriting layers 2–4 of the architecture for each input — not feasible.

An internal toolpath IR is still a reasonable alternative for a future
project that doesn't need the editor's preview pane. We don't.
