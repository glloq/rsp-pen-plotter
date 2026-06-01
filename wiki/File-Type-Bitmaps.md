# Bitmaps

PNG, JPG, TIFF, WebP, HEIC and HEIF — anything Pillow + `pillow-heif` can
open. OmniPlot doesn't print pixels: it converts the raster to plotter
strokes via one of the 25+ raster algorithms.

## Pre-processing

Before any algorithm runs, the converter:

1. **decodes** the file with Pillow (auto-rotates EXIF orientation)
2. **caps total pixels** at `MAX_PIXELS` (12 megapixels) — bigger images
   are downscaled. Plotter resolution is the pen tip, not the source — a
   24 MP photo gives no extra detail.
3. **normalises the colour mode** to RGBA so downstream algorithms can
   reason about transparency
4. **(optionally) colour-separates** into N pen layers via k-means
   (`scikit-learn`)

The MAX_PIXELS cap is a class attribute on `BitmapConverter` if you ever
need to bump it for an outlier file.

## Choosing the algorithm

See [Picking the right algorithm](Picking-the-Right-Algorithm.md). The
short version:

- **photo, shaded** → `stippling`, `crosshatch`, `halftone`, `flowfield`
- **logo, line art** → `direct` (potrace)
- **technical drawing** → `edges` or `centerline`
- **decorative / generative** → `truchet`, `brick`, `voronoi_stipple`

## Colour separation

The editor's *Colours* step splits the bitmap into N pen layers. Two paths:

- **k-means** (default for photos) — clusters pixels into K dominant
  colours; each cluster becomes a layer
- **palette match** — when the operator has a fixed pen palette, the
  separator quantises to those exact colours instead

Each colour layer can use a different algorithm. Common recipe for
two-pen portraits:

- layer 1 (skin / mid-tones) — `crosshatch`, sparse, light pen
- layer 2 (shadows / darks) — `crosshatch`, dense, dark pen

## HEIC / HEIF (iPhone)

Works out of the box on a Pi with `pillow-heif` installed (the appliance
installer takes care of it). On Apple-encoded multi-frame HEIC files,
OmniPlot reads the primary image only.

## When to skip OmniPlot

If you've already produced a vector — *e.g.* from Photoshop "Image →
Trace" or Affinity Designer — export to SVG instead and feed that
directly. OmniPlot keeps your authoring layers; the bitmap path
re-vectorises and loses any structure you built upstream.

## See also

- [Picking the right algorithm](Picking-the-Right-Algorithm.md)
- [Multi-pass plotting](Multi-Pass-Plotting.md)
- [`docs/converters.md`](../docs/converters.md)
