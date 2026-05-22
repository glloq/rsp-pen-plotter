# Adding a Converter

Supporting a new input format means writing one converter plugin. The rest of
the pipeline (layer extraction, optimization, G-code generation, simulation,
streaming) is untouched because everything downstream operates on the SVG pivot.

## The contract

A converter subclasses `Converter` (`converters/base.py`), declares the MIME
types it handles, and implements `convert`:

```python
from typing import Any, ClassVar

from pen_plotter.converters.base import ConversionResult, Converter


class MyFormatConverter(Converter):
    """Normalize MyFormat files to the SVG pivot."""

    supported_mimes: ClassVar[frozenset[str]] = frozenset({"application/x-myformat"})

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        svg = _myformat_to_svg(data)  # your logic
        return ConversionResult(svg=svg, source_mime="application/x-myformat")
```

`ConversionResult` carries the `svg`, the `source_mime`, optional `warnings`,
and freeform `metadata`.

## The SVG pivot output contract

Emit a self-contained SVG document and follow these rules so the rest of the
pipeline understands it:

- Declare both the SVG and Inkscape namespaces on the root element.
- Put each drawing layer in a **top-level `<g>` with an `inkscape:label`**.
  Layer extraction (`core/layers.py`, via `labeled_group_fragments`) maps one
  layer per labeled group; an SVG with no labeled groups is treated as a single
  `layer-1`.
- Prefer stroked paths over fills — a pen draws lines, not areas. (Optimization
  will convert fills to outlines, but emitting strokes is cleaner.)
- Use a `viewBox` so geometry is measured in user units. For text-like output,
  millimeter user units map directly onto the workspace.

`typography/hershey.py` is a good reference for a well-formed pivot document.

## Registering it

Add the converter to the built-in set in `converters/defaults.py` so both the
app and the tests pick it up:

```python
from pen_plotter.converters.myformat import MyFormatConverter

converters = [
    SvgConverter(),
    # …existing…
    MyFormatConverter(),
]
```

Registration is idempotent and rejects MIME collisions
(`registry.register` raises `ValueError` if a type is already claimed).

## Testing

Add a test under `backend/tests/` that feeds a small fixture through your
converter and asserts the output parses as SVG and exposes the expected labeled
groups. The existing `test_bitmap.py`, `test_vector.py`, and `test_document.py`
show the pattern; `test_upload.py` covers end-to-end dispatch through the
registry.
