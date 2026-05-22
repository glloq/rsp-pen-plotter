# Converters & Raster Algorithms

A converter turns raw uploaded bytes into the normalized SVG pivot. Each
converter declares the MIME types it handles; `converters/registry.py` indexes
them and `converters/defaults.py` registers the built-in set at startup.

## Supported input formats

| Converter | MIME types | Backend |
| --- | --- | --- |
| `SvgConverter` | `image/svg+xml` | Passthrough + sanitization |
| `BitmapConverter` | PNG/JPEG/TIFF/WebP/HEIC (Pillow + pillow-heif) | Color quantization + raster algorithm |
| `PdfConverter` | `application/pdf` | Vector extraction via PyMuPDF |
| `DxfConverter` | DXF MIME types | `ezdxf` |
| `EpsConverter` | EPS/AI MIME types | Ghostscript subprocess → PDF → vectors |
| `TextConverter` | `text/plain` | Hershey single-stroke layout |
| `MarkdownConverter` | `text/markdown` | markdown-it + Hershey (sized blocks) |
| `HtmlConverter` | `text/html` | WeasyPrint |
| `DocumentConverter` | DOCX/ODT/RTF | LibreOffice headless subprocess → PDF |

The `gcode` converter bypasses the pipeline and streams uploaded G-code
directly.

## Raster algorithms

For bitmap input, the converter applies a raster-art strategy chosen by the
user. Algorithms are registered by name in
`converters/algorithms/__init__.py`; only fully implemented ones are exposed:

| Name | Class | Output |
| --- | --- | --- |
| `direct` | `DirectVectorizationAlgorithm` | potrace outline tracing of color masks |
| `halftone` | `HalftoneAlgorithm` | Variable-density dot/line halftone |
| `stippling` | `StipplingAlgorithm` | Stippled dot field by local intensity |

`GET /algorithms` returns the available choices and their option schemas for the
UI. `get_algorithm(name)` resolves one (raising `KeyError` for unknown names).

## External tool dependencies

Some converters shell out to system binaries (always with positional arguments
inside an isolated temp directory — never through a shell):

- **potrace** — bitmap → vector outlines
- **ghostscript** — EPS/AI rasterization
- **libreoffice** — office documents → PDF
- **WeasyPrint** — HTML → PDF (Python library, but pulls native deps)

Install these on the host for the corresponding formats to work; the simulator
and core pipeline do not require them.
