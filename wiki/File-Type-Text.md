# Text & Markdown

For raw text, OmniPlot uses **Hershey single-stroke fonts** — the
classic vector fonts engraving and plotting machines have used since
the 1960s. Single-stroke means each glyph is a polyline, not a filled
outline: the pen draws once and moves on. Perfect for plotting; lousy
for screen reading.

## Plain text (`.txt`)

The text converter:

1. reads the file as UTF-8 (falls back to latin-1)
2. lays out the text in a fixed page size (defaults to A4) with the
   active Hershey font
3. honours basic typographic options: font, font size, line height, page
   margin, justification

You can change the font in the editor (the *Render* step). `GET /fonts`
returns the list bundled with the install.

### Bundled Hershey fonts

- `hershey:sans` — Roman, sans-serif
- `hershey:serif` — Roman, serif
- `hershey:script` — script / handwriting feel
- `hershey:gothic` — blackletter
- `hershey:cyrillic`, `hershey:greek` — non-Latin alphabets

(See `GET /fonts` for the exact, version-pinned list.)

## Markdown (`.md`)

The Markdown converter wraps the plain-text converter with structure
awareness:

- **headings** (`#`, `##`, …) → progressively larger font sizes
- **bold** / **italic** → font swap (`hershey:sans` → `hershey:sans-bold`,
  `hershey:serif-italic`)
- **lists** — bullet character + hanging indent
- **block quotes** — indented, italic font
- **code spans / fences** — `hershey:monospace`
- **horizontal rules** — straight line across the column
- **inline links** — text only (URLs aren't plotted unless you write them
  out)

What is **not** rendered:

- images — Markdown image syntax is dropped; embed the image as a
  separate placement instead
- tables — Markdown tables are not yet rendered
- HTML inside Markdown — escaped to plain text

## Wrapping & layout

Both `.txt` and `.md` flow text into the available column at the chosen
font size. The editor's *Render* step lets you pick:

- font size (in mm)
- line height multiplier
- alignment: left, center, justify
- page margin (per side, in mm)

The placement on the sheet defines the column width — drag the right
handle to widen the column, and the text re-flows.

## Multi-page text

If the text overflows one page, OmniPlot emits one SVG per page; the
editor places them side-by-side by default, but you can also queue them
as separate plots.

## When to skip the text converter

If your text is the headline of a poster designed in Inkscape or
Illustrator, **convert it to paths** in your design tool first and
export the whole thing as SVG. You get full type control, and Hershey
limitations no longer apply.

## See also

- [Documents](File-Type-Documents.md)
- [Supported file types](Supported-File-Types.md)
- [`docs/converters.md`](../docs/converters.md)
