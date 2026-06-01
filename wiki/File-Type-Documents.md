# Documents — DOCX, ODT, RTF, HTML

OmniPlot can plot a typeset document. The pipeline goes through PDF on the
way to the SVG pivot.

## DOCX, ODT, RTF

These rely on **headless LibreOffice**. The converter:

1. writes the upload to a temp file
2. invokes `libreoffice --headless --convert-to pdf` in an isolated user
   profile (so concurrent conversions don't trample each other)
3. passes the resulting PDF to the PDF converter
4. by default extracts page 1 — pick another page in the editor

### Install

The appliance installer takes care of this (`apt install
libreoffice-writer`). On a manual dev machine:

```bash
sudo apt install libreoffice-writer  # Debian / Ubuntu
brew install --cask libreoffice      # macOS
```

If the converter shows *"LibreOffice not found"*, either install the
package or set `OMNIPLOT_LIBREOFFICE_BIN=/path/to/soffice`.

### Why LibreOffice and not `python-docx`?

`python-docx` reads the XML but doesn't render layout — fonts, line
breaks, page breaks, tables, images, footnotes. LibreOffice gives us a
true rendered page, which is what the operator expects to see plotted.

The price is a per-conversion subprocess (~2–4 s on a Pi 4). The
backend caches the resulting PDF so toggling between pages is fast.

## HTML

The HTML converter uses **WeasyPrint** (a Python library) to render
HTML + CSS to PDF, then hands the PDF over to the PDF converter.

WeasyPrint is print-quality (it's a CSS Paged Media implementation, not a
headless browser) so layout is predictable. Things it doesn't support:

- JavaScript — turn it off in your source HTML (or pre-render it
  separately and paste the resulting HTML)
- Web fonts loaded via `@font-face` from remote URLs — they may load
  depending on the Pi's network policy. Self-host fonts in the HTML's
  asset folder for reliability.
- complex flex / grid layouts on older WeasyPrint releases — the
  appliance installer pins a known-good version

A typical recipe: take a Hugo / Jekyll post, run it through Pandoc or
WeasyPrint locally, point OmniPlot at the resulting `.html`.

## What plots well

- typeset text — paragraphs, headings, lists
- tables (drawn as the cell borders)
- embedded vector images
- embedded raster images (re-vectorised, default `direct`)

## What doesn't plot well

- multi-column complex layouts — the per-page extraction stays accurate,
  but the result is dense
- documents with photo backgrounds — converts to fill stipple by default,
  which can dominate the page; consider stripping backgrounds first
- bidirectional / RTL languages — works at the text level, but Hershey
  fonts (used for raw `.txt` / `.md`) don't include Arabic / Hebrew
  shapes; the *document* path goes through LibreOffice so its font
  handling applies

## See also

- [Text & Markdown](File-Type-Text.md)
- [Vectors (PDF, EPS)](File-Type-Vectors.md)
- [`docs/converters.md`](../docs/converters.md)
