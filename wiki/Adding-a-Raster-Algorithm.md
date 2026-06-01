# Adding a raster algorithm

OmniPlot's raster algorithms turn a bitmap layer into plotter strokes.
Adding one is roughly:

1. write a class deriving from `RasterAlgorithm`
2. register it in `converters/algorithms/__init__.py`
3. declare its **kind** (fill / lines / mono_stroke) and **complexity**
   (low / medium / high)
4. add a unit test
5. (optional) add option metadata so the editor renders nice controls

If you want to add a *new file format*, see
[`docs/adding_a_converter.md`](../docs/adding_a_converter.md) instead.

## The base class

```python
from typing import ClassVar
from pen_plotter.converters.algorithms.base import RasterAlgorithm

class MyAlgorithm(RasterAlgorithm):
    name: ClassVar[str] = "my_algo"

    def render(
        self,
        image: PIL.Image.Image,
        *,
        options: dict[str, Any] | None = None,
    ) -> RasterRenderResult:
        # produce SVG-pivot fragments (one <g> per layer)
        ...
```

`render` is allowed to be slow (it runs in a thread pool), but should
respect the abort signal so the editor's debounced rerender can cancel
in-flight work.

## A worked example — diagonal hatching

```python
# backend/pen_plotter/converters/algorithms/diagonal.py
from __future__ import annotations
import math
from typing import Any, ClassVar
import numpy as np
import PIL.Image
from pen_plotter.converters.algorithms.base import (
    RasterAlgorithm,
    RasterRenderResult,
)

class DiagonalHatchAlgorithm(RasterAlgorithm):
    name: ClassVar[str] = "diagonal_hatch"

    def render(
        self,
        image: PIL.Image.Image,
        *,
        options: dict[str, Any] | None = None,
    ) -> RasterRenderResult:
        opts = options or {}
        angle_deg = float(opts.get("angle_deg", 45))
        spacing_mm = float(opts.get("spacing_mm", 1.0))
        density = float(opts.get("density", 0.7))

        gray = np.asarray(image.convert("L"), dtype=np.float32) / 255.0
        h, w = gray.shape

        lines: list[str] = []
        theta = math.radians(angle_deg)
        sin_t, cos_t = math.sin(theta), math.cos(theta)

        # walk across the image, emit a line every spacing_mm
        diag = int(math.hypot(w, h))
        for s in range(-diag, diag, max(1, int(spacing_mm * 4))):
            x0 = s * cos_t
            y0 = s * sin_t
            # tone-modulated: skip when local intensity > (1 - density)
            local = gray[int(min(max(y0, 0), h - 1)),
                         int(min(max(x0, 0), w - 1))]
            if local > density:
                continue
            x1 = x0 - diag * sin_t
            y1 = y0 + diag * cos_t
            x2 = x0 + diag * sin_t
            y2 = y0 - diag * cos_t
            lines.append(
                f'<line x1="{x1:.2f}" y1="{y1:.2f}" '
                f'x2="{x2:.2f}" y2="{y2:.2f}" '
                f'stroke="black" stroke-width="0.3"/>'
            )

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<g inkscape:label="hatch">'
            + "".join(lines)
            + '</g></svg>'
        )
        return RasterRenderResult(svg=svg, warnings=[])
```

## Register it

```python
# backend/pen_plotter/converters/algorithms/__init__.py
from pen_plotter.converters.algorithms.diagonal import DiagonalHatchAlgorithm

_ALGORITHMS: dict[str, RasterAlgorithm] = {
    algo.name: algo
    for algo in (
        # … existing algorithms …
        DiagonalHatchAlgorithm(),
    )
}

_KINDS["diagonal_hatch"] = "fill"
_COMPLEXITY["diagonal_hatch"] = "medium"
```

That's it backend-side. `GET /algorithms` now lists it, the editor
shows a card for it.

## Option schema (for the editor)

The editor reads option metadata from `algo.options_schema()` (a
JSON-Schema-shaped dict) to render controls. Defaults are reasonable
without it, but you'll get a generic textbox per option. Override to
get sliders / dropdowns:

```python
def options_schema(self) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "angle_deg": {
                "type": "number", "minimum": 0, "maximum": 180,
                "default": 45, "ui:widget": "slider",
            },
            "spacing_mm": {
                "type": "number", "minimum": 0.2, "maximum": 5,
                "default": 1.0, "ui:widget": "slider",
            },
            "density": {
                "type": "number", "minimum": 0, "maximum": 1,
                "default": 0.7, "ui:widget": "slider",
            },
        },
    }
```

## Test

```python
# backend/tests/converters/algorithms/test_diagonal.py
import PIL.Image
from pen_plotter.converters.algorithms.diagonal import DiagonalHatchAlgorithm

def test_renders_some_lines():
    image = PIL.Image.new("L", (200, 200), 0)        # all dark → all lines
    result = DiagonalHatchAlgorithm().render(image)
    assert "<line" in result.svg
    assert result.warnings == []

def test_empty_on_white_input():
    image = PIL.Image.new("L", (200, 200), 255)      # all white → no lines
    result = DiagonalHatchAlgorithm().render(image, options={"density": 0.5})
    assert "<line" not in result.svg
```

Run the suite with `cd backend && uv run pytest`.

## Editor recommendation (optional)

To have the Assistant wizard recommend your algorithm for some
(source, goal) pair, edit the recommendation table in
`backend/pen_plotter/api/policy.py`. Each entry is a
`(source_kind, goal) → (algorithm, options)` mapping plus a confidence
score. The wizard picks the highest-scoring entry; ties break
deterministically.

## Front-end card style (optional)

If you want a custom icon or grouping for your algorithm card, edit
`frontend/src/components/edit/RenderTab.vue` — algorithms are listed
from `GET /algorithms` and rendered with a default card unless an
override is provided.

## See also

- [Picking the right algorithm](Picking-the-Right-Algorithm.md)
- [`docs/converters.md`](../docs/converters.md)
- [`docs/adding_a_converter.md`](../docs/adding_a_converter.md)
- [`docs/plugin-sdk.md`](../docs/plugin-sdk.md)
