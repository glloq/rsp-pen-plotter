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

There is no raw G-code *upload* path — G-code never goes through the
converter pipeline. It enters the system only through the API, as the body
of `POST /queue` (enqueue a print run) or `POST /plotter/run` (stream a job
immediately).

## Raster algorithms

For bitmap input, the operator picks a raster-art strategy in the editor.
Algorithms are registered by name in
`backend/pen_plotter/converters/algorithms/__init__.py` — 51 registered, of
which 47 are visible in the editor's pickers (see the hidden flag below).
Each carries:

- a **kind** — `fill` (packs ink across a region), `lines` (discrete
  outlines) or `mono_stroke` (single continuous polyline)
- a **complexity** hint (`low` / `medium` / `high`) used by the editor to
  warn before slow previews.

| Name | Kind | Complexity | What it does |
| --- | --- | --- | --- |
| `direct` | fill | low | potrace outline of tonal masks |
| `halftone` | fill | low | regular grid of variable-size dots, optional per-ink screen angle (tone-aware: dot size follows cell darkness) |
| `stippling` | fill | medium | randomly scattered dot field by intensity (tone-aware: dots pulled toward dark pixels) |
| `crosshatch` | fill | medium | parallel strokes, optional crossed 90° pass and `joined` zig-zag mode (tone-aware: extra rotated passes per darkness band) |
| `contours` *(hidden)* | lines | low | concentric inner outlines — topographic-map feel (tone-aware: luminance iso-lines) |
| `edges` | lines | low | traced region boundary — line-art / technical style |
| `centerline` | lines | medium | medial-skeleton single-stroke polylines |
| `spiral` | mono_stroke | medium | single Archimedean spiral clipped to the mask, tone-modulated |
| `scanlines` | mono_stroke | low | horizontal scan lines, flat or sinusoidal (tone-aware: wave amplitude follows darkness) |
| `tsp` *(hidden)* | mono_stroke | high | legacy greedy nearest-neighbour tour through stipple points |
| `hilbert` | mono_stroke | medium | Hilbert space-filling curve, optionally tone-adaptive |
| `gosper` | mono_stroke | medium | Gosper / flowsnake space-filling stroke (tone-aware: blank highlights + rotated dark overlay) |
| `eulerian_hatch` *(hidden)* | fill | medium | hatches stitched into one continuous zig-zag per island (tone-aware: extra rotated passes per darkness band) |
| `concentric_offset` | mono_stroke | medium | inward erosion spiral — very few pen-lifts (tone-aware: ring wobble follows darkness) |
| `flowfield` | fill | high | streamlines following the image gradient or smooth noise (tone-aware) |
| `tsp_opt` | mono_stroke | high | TSP tour with 2-opt / MST optimisation, kd-tree neighbours (tone-aware: seeds weighted by darkness) |
| `voronoi_stipple` | fill | high | centroidal Voronoi stippling, darkness-weighted (tone-aware) |
| `squiggle` | mono_stroke | medium | wiggly lines with amplitude / frequency drift (tone-aware: both follow darkness) |
| `lowpoly` | lines | high | Delaunay triangulation over sampled points, drawn as edges (tone-aware: smaller facets where darker) |
| `scribble` | fill | medium | wobbly, overshooting strokes — loose pencil feel (tone-aware: extra crossing passes per darkness band) |
| `grid` *(hidden)* | lines | low | square mesh of horizontal + vertical strokes |
| `brick` | lines | low | running-bond courses with staggered joints |
| `dashes` | fill | medium | hatch sweep chopped into short dashes |
| `truchet` | lines | low | randomly oriented Truchet diagonals per cell |
| `rings` | mono_stroke | medium | concentric circles about the region centroid |
| `sunburst` | mono_stroke | medium | radial rays fanning out from the centroid |
| `circle_pack` | fill | high | dart-throwing non-overlapping circle packing |
| `ridge_lines` | fill | low | rows displaced upward by darkness — the pulsar-plot ridge texture |
| `hitomezashi` | lines | low | sashiko stitch rows/columns weaving an interlocking pattern |
| `cubic_disarray` | lines | low | grid of squares tumbling into disorder where darkest (Schotter) |
| `quadtree` | lines | medium | recursive square subdivision — tone becomes cell density |
| `maze` | lines | medium | perfect maze carved as a random spanning tree over the region |
| `phyllotaxis` | fill | medium | sunflower-spiral dots sized by local darkness |
| `voronoi_mosaic` | lines | high | cracked-glaze Voronoi cell walls, smaller cells where darker |
| `curve_stitching` | lines | low | per-cell chord fans — the nail-and-thread op-art envelope |
| `string_art` | mono_stroke | high | one continuous thread between rim pegs, chords stacked by darkness |
| `space_colonization` | lines | high | organic veins growing toward dark areas — root / lightning texture |
| `penrose` | lines | medium | aperiodic five-fold Penrose (P3) rhombi clipped to the region |
| `dither` | fill | medium | error-diffusion dots (Floyd–Steinberg / Atkinson / Bayer) |
| `etch` | fill | medium | short engraving strokes along isophotes, denser where darker |
| `noise_contours` | lines | medium | tone iso-lines warped by fractal noise — marbled topography |
| `reaction_diffusion` | fill | high | Gray–Scott Turing spots/stripes grown inside the region |
| `superpixel_hatch` | fill | high | SLIC superpixels hatched along their dominant orientation |
| `moire` | lines | low | two offset ring/line gratings beating into op-art fringes |
| `weave` | lines | low | basket weave — interlacing over/under ribbons |
| `honeycomb` | lines | low | hexagonal lattice, optionally tone-scaled cells |
| `harmonograph` | mono_stroke | medium | damped twin-pendulum figure as one long decaying stroke |
| `attractor` | fill | medium | chaotic orbit (de Jong / Clifford) scattered as smoky filaments |
| `text_fill` | fill | medium | rows of repeated single-stroke text as shading texture |
| `lsystem` | lines | medium | dragon curve / plant / Koch island / Sierpiński arrowhead |
| `chladni` | lines | low | nodal lines of a vibrating plate — resonance sand patterns |

### Hidden algorithms

Four entries carry the **hidden** flag (`_HIDDEN` in the registry): they stay
fully registered — persisted placements and presets that reference them keep
rendering — but the editor's pickers no longer offer them for *new* layers,
because each is a strict or near duplicate of a better-tuned visible entry:

| Hidden | Superseded by |
| --- | --- |
| `tsp` | `tsp_opt` — `method: nn` is byte-equivalent, the other methods strictly better |
| `grid` | `crosshatch` with `angle_deg: 0` + `crossed: true` |
| `eulerian_hatch` | `crosshatch` with `joined: true` |
| `contours` | `concentric_offset` — marching-squares quality vs the deliberately approximate hull walk |

`GET /algorithms` returns the available choices, their option schemas, kinds,
complexity hints and the hidden flag; the canonical wire format is the
manifest at `/manifests/algorithms`. The frontend uses this to group
algorithm cards in the editor and to pre-warn on slow previews.

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
