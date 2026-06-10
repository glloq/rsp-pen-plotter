# Bitmaps

PNG, JPG, TIFF, WebP, HEIC and HEIF — anything Pillow + `pillow-heif` can
open. OmniPlot doesn't print pixels: it converts the raster to plotter
strokes via one of the 47 visible raster algorithms (51 registered — four
hidden legacy duplicates).

## Pre-processing

Before any algorithm runs, the converter:

1. **decodes** the file with Pillow (`pillow-heif` registered for
   HEIC/HEIF) and **normalises the colour mode to RGB**
2. **rejects oversized images** — anything above `MAX_PIXELS`
   (16 megapixels) fails with an error asking you to resize the source or
   split the plot. The guard reads the header only, so a decompression
   bomb is refused before any RAM is committed. Plotter resolution is the
   pen tip, not the source — a 24 MP photo gives no extra detail anyway.
3. **applies the Image-tab adjustments** (crop, rotate, flip, levels,
   gamma, brightness/contrast, blur/sharpen, auto-contrast)
4. **downscales** to the segmentation canvas (the detail tier you pick in
   the SVG tab; 800 px by default)
5. **(optionally) dithers** — the Floyd–Steinberg dither from the Image
   tab runs *after* the downscale, at segmentation resolution, so the dot
   texture survives instead of being averaged away by the resize
6. **(optionally) colour-separates** into N pen layers via k-means
   (`scikit-learn`)

The `MAX_PIXELS` cap is a module constant in
`backend/pen_plotter/converters/bitmap/preprocess.py` if you ever need to
bump it for an outlier file.

## Choosing the algorithm

See [Picking the right algorithm](Picking-the-Right-Algorithm.md). The
short version:

- **photo, shaded** → `stippling`, `crosshatch`, `halftone`, `flowfield`
- **photo, engraving / retro print** → `etch`, `dither`, `text_fill`
- **photo, organic** → `phyllotaxis`, `superpixel_hatch`,
  `reaction_diffusion`, `noise_contours`
- **logo, line art** → `direct` (potrace)
- **technical drawing** → `edges` or `centerline`
- **one continuous stroke** → `tsp_opt`, `hilbert`, `spiral`, `string_art`
- **decorative / generative** → `truchet`, `brick`, `voronoi_stipple`,
  `maze`, `penrose`, `lsystem`, `chladni`

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
