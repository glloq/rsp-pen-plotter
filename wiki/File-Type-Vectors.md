# Vectors — SVG, PDF, EPS, DXF

Vector inputs skip the raster algorithm step entirely: the converter
sanitises and normalises the document, then layers go straight into the
toolpath pipeline.

## SVG

The reference format. The converter:

- runs the SVG through a strict sanitiser (no scripts, no external
  references, no `<foreignObject>`)
- extracts groups: any top-level `<g>` carrying an `inkscape:label` becomes
  one OmniPlot layer; otherwise groups are inferred from `stroke` / `fill`
  attributes
- preserves the original viewBox; units default to mm if explicit `mm`
  units are used, otherwise user units

### Author tips

- **Inkscape**: use Layers (Object → Layers) — one per pen colour. The
  `inkscape:label` is OmniPlot's layer name.
- **Illustrator**: top-level groups with names become layers.
- **Figma**: export each "Frame" or layer separately, or use the *Save as
  SVG* with *include "id" attribute* turned on.
- **Generative scripts** (p5.js, paper.js, vsketch): set `stroke` per
  group and OmniPlot will split colours automatically.

### What doesn't work

- gradients (stroke or fill) — fills are not plotted; stroked paths only
- text as `<text>` — convert to paths before exporting, or use Markdown
  input
- clipping paths — flattened away by the sanitiser
- filters (`<filter>`) — dropped

## PDF

PyMuPDF extracts vectors per page. The editor lets you pick which page
plots. Embedded rasters are vectorised inline using the bitmap pipeline
(default algorithm: `direct`), so a magazine page with text + photos
becomes a mixed layer set.

Per-page PDFs work; multi-up imposed PDFs need to be split with another
tool first.

## EPS / PS / AI

Ghostscript renders the PostScript to a temporary PDF, then the PDF path
takes over. AI files older than CS3 don't carry a PDF wrapper and may
fail — re-save them from Illustrator with *PDF Compatible* enabled.

EPS rasters embedded in the PostScript stream are extracted and
re-vectorised the same way the PDF converter handles them.

## DXF

AutoCAD's interchange format. `ezdxf` reads the file, the converter
walks every entity in every layer:

- **Lines, polylines, arcs, splines** → polylines
- **Circles, ellipses** → sampled polylines
- **TEXT / MTEXT** → Hershey single-stroke text (configurable via
  `hershey_text`, `font`, `stroke_width_mm`)
- **DIMENSIONs** → drawn as the underlying lines (no rendering of the
  arrowheads or extension lines)
- **INSERTs** (block references) → expanded inline

The conversion respects the DXF layer structure — each DXF layer becomes
one OmniPlot layer, named after the DXF layer name.

### When DXF fails

DXF is a famously loose format. If `ezdxf` rejects a file:

- save it from a recent AutoCAD / LibreCAD as "AutoCAD 2018 DXF"
- run it through Open Design Alliance's `TeighaFileConverter` first
- as a last resort, export to SVG from the source CAD instead

## Coordinates, units, scale

Every vector converter targets the SVG pivot in **millimetres**. PDF
and EPS rely on the PDF's `MediaBox`; DXF respects the file header's
`$INSUNITS`; SVG uses its `viewBox` interpreted at the unit declared on
the root element.

The editor's *Sheet* tab re-scales the placement to fit the chosen paper
size — the original coordinate system is only used to compute aspect
ratio.

## See also

- [Supported file types](Supported-File-Types.md)
- [Machine profiles](Machine-Profiles.md)
- [`docs/converters.md`](../docs/converters.md)
