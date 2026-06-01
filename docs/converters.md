# Converters & raster algorithms

A converter turns raw uploaded bytes into the normalised SVG pivot. Each
converter declares the MIME types it handles; `converters/registry.py` indexes
them and `converters/defaults.py` registers the built-in set at startup.

## Supported input formats

| Converter | Extensions | MIME types | Backend |
| --- | --- | --- | --- |
| `SvgConverter` | `.svg` | `image/svg+xml` | Passthrough + sanitisation |
| `BitmapConverter` | `.png` `.jpg` `.jpeg` `.tiff` `.webp` `.heic` `.heif` | `image/png`, `image/jpeg`, `image/tiff`, `image/webp`, `image/heic`, `image/heif` | Pillow + pillow-heif, then a raster algorithm |
| `PdfConverter` | `.pdf` | `application/pdf` | Vector extraction via PyMuPDF, per page |
| `DxfConverter` | `.dxf` | `image/vnd.dxf`, `application/dxf`, `image/x-dxf` | `ezdxf`; `TEXT`/`MTEXT` → Hershey single-stroke polylines |
| `EpsConverter` | `.eps` `.ps` `.ai` | `application/postscript`, `application/eps`, `image/eps`, `image/x-eps` | Ghostscript subprocess → PDF → vectors; embedded rasters re-vectorised |
| `TextConverter` | `.txt` | `text/plain` | Hershey single-stroke layout |
| `MarkdownConverter` | `.md` | `text/markdown` | `markdown-it-py` + Hershey, heading sizes preserved |
| `HtmlConverter` | `.html` | `text/html` | WeasyPrint → PDF → vectors |
| `DocumentConverter` | `.docx` `.odt` `.rtf` | Office MIMEs | `libreoffice --headless` → PDF → first page |

The `gcode` upload path bypasses the converter pipeline and streams uploaded
G-code directly to the queue.

## Raster algorithms

For bitmap input, the operator picks a raster-art strategy in the editor.
Algorithms are registered by name in
`backend/pen_plotter/converters/algorithms/__init__.py`. Each carries:

- a **kind** — `fill` (packs ink across a region), `lines` (discrete
  outlines) or `mono_stroke` (single continuous polyline)
- a **complexity** hint (`low` / `medium` / `high`) used by the editor to
  warn before slow previews.

| Name | Kind | Complexity | What it does |
| --- | --- | --- | --- |
| `direct` | fill | low | potrace outline of tonal masks |
| `halftone` | fill | low | uniform dot grid, radius follows tone |
| `stippling` | fill | medium | Poisson-disk dot field by intensity |
| `crosshatch` | fill | medium | parallel-stroke shading per tonal band |
| `contours` | lines | low | iso-contour outlines |
| `edges` | lines | low | edge-detected outlines (Sobel / Canny) |
| `centerline` | lines | medium | skeletonised mid-lines |
| `spiral` | mono_stroke | medium | continuous tone-modulated spiral |
| `scanlines` | mono_stroke | low | raster sweep with tone-mapped jitter |
| `tsp` | mono_stroke | high | TSP tour through stipple points |
| `tsp_opt` | mono_stroke | high | TSP + 2-opt with kd-tree neighbours |
| `hilbert` | mono_stroke | medium | space-filling Hilbert curve at chosen depth |
| `gosper` | mono_stroke | medium | Gosper / flowsnake fill |
| `eulerian_hatch` | fill | medium | hatching as a single Eulerian path |
| `concentric_offset` | mono_stroke | medium | inward offsetting outlines |
| `flowfield` | fill | high | streamlines following image gradients |
| `voronoi_stipple` | fill | high | Lloyd-relaxed weighted Voronoi stippling |
| `squiggle` | mono_stroke | medium | wavy sub-pixel scan row |
| `lowpoly` | lines | high | Delaunay triangulation over sampled points |
| `scribble` | fill | medium | wobble polyline per scan run |
| `grid` | lines | low | two clipped line sweeps |
| `brick` | lines | low | staggered course lines |
| `dashes` | fill | medium | hatch sweep chopped into dashes |
| `truchet` | lines | low | one Truchet diagonal per cell |
| `rings` | mono_stroke | medium | concentric ring sampling |
| `sunburst` | mono_stroke | medium | radial ray sampling |
| `circle_pack` | fill | high | dart-throwing circle packing |

`GET /algorithms` returns the available choices, their option schemas, kinds
and complexity hints — the frontend uses this to group algorithm cards in the
editor and to pre-warn on slow previews.

## External tool dependencies

Some converters shell out to system binaries (always with positional arguments
inside an isolated temp directory — never through a shell):

- **potrace** — bitmap → vector outlines
- **ghostscript** — EPS / AI rasterisation
- **libreoffice** (`soffice`) — office documents → PDF
- **WeasyPrint** — HTML → PDF (Python library, native deps)

Install these on the host for the corresponding formats to work; the
simulator and the core pipeline do not require them.

## Colour separation

Independently of the algorithm, the editor can split a raster into N
plottable colour layers via k-means quantisation (`scikit-learn`). Each
colour becomes its own SVG layer, mapped to its own pen slot. SVG inputs
keep their authoring layers (`<g inkscape:groupmode="layer">` or any group
with a `stroke`/`fill` attribute).
