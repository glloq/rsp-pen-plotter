# Supported file types

OmniPlot accepts every common 2D-art format, normalises each one to a single
**SVG pivot**, then runs the same toolpath / G-code pipeline regardless of
where the SVG came from.

The frontend's file picker advertises this exact list — anything else gets a
"format not supported" toast before upload.

## Bitmaps → vectorised

The bitmap converter loads via Pillow (with `pillow-heif` for HEIC/HEIF), then
the operator picks a raster-art **algorithm** (see [Picking the right
algorithm](Picking-the-Right-Algorithm.md)).

| Extension | MIME | Notes |
| --- | --- | --- |
| `.png` | `image/png` | Lossless; ideal source for line art |
| `.jpg` `.jpeg` | `image/jpeg` | Most common photo format |
| `.tiff` | `image/tiff` | Multi-layer not supported — first layer only |
| `.webp` | `image/webp` | Lossy and lossless variants both work |
| `.heic` | `image/heic` | iPhone photos (`pillow-heif`). The picker lists `.heic` only — rename a `.heif` (the backend converter accepts both MIMEs over the API) |

→ [Bitmaps in detail](File-Type-Bitmaps.md)

## Vectors & CAD → pass-through

| Extension | MIME | Notes |
| --- | --- | --- |
| `.svg` | `image/svg+xml` | Sanitised then passed through; layers preserved |
| `.pdf` | `application/pdf` | Per-page selection; embedded rasters re-vectorised |
| `.eps` `.ps` `.ai` | `application/postscript`, `application/eps`, `image/eps`, `image/x-eps` | Ghostscript → PDF → vectors |
| `.dxf` | `image/vnd.dxf`, `application/dxf`, `image/x-dxf` | CAD; `TEXT`/`MTEXT` → Hershey strokes |

→ [Vectors in detail](File-Type-Vectors.md)

## Documents → PDF → SVG

| Extension | MIME | Notes |
| --- | --- | --- |
| `.docx` | Office MIME | LibreOffice `--headless` |
| `.odt` | LibreOffice MIME | LibreOffice `--headless` |
| `.rtf` | `application/rtf`, `text/rtf` | LibreOffice `--headless` |
| `.html` | `text/html` | WeasyPrint (Python lib, native deps) |

The DOCX / ODT / RTF path needs `libreoffice` on the host (the appliance
installer installs `libreoffice-writer`). The HTML path needs WeasyPrint's
native dependencies (Cairo, Pango).

→ [Documents in detail](File-Type-Documents.md)

## Text → Hershey strokes

| Extension | MIME | Notes |
| --- | --- | --- |
| `.txt` | `text/plain` | Single-stroke Hershey layout |
| `.md` | `text/markdown` | Headings, bold, italic preserved via font swaps |

→ [Text in detail](File-Type-Text.md)

## Raw G-code → API only

Raw G-code is **not an upload type** — the picker doesn't accept `.gcode`
files and the converter pipeline has nothing to convert. Hand the program
to the backend directly: `POST /queue` (durable, resumable) or
`POST /plotter/run` (immediate), each with a `gcode` string in the body.
The dialect must match the target machine profile — there's no
translation.

→ [Raw G-code in detail](File-Type-Gcode.md)

## Format detection

OmniPlot resolves the format from the **client-supplied `Content-Type`
header**, falling back to the filename extension (Python's `mimetypes`)
when the header is missing or `application/octet-stream`. There is **no
magic-byte sniffing** — a mislabelled file is routed by its claimed type.
Unknown types are rejected at upload time with a 415 — there's no silent
fallback.

## What about format X?

Anything with a documented vector format is a one-evening converter plugin
away. See [Adding a converter](../docs/adding_a_converter.md).
