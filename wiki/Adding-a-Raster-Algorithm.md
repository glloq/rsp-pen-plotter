# Adding a raster algorithm

OmniPlot's raster algorithms turn one binary colour region (a mask over the
source image) into plotter strokes. Adding one is roughly:

1. write a class deriving from `RasterAlgorithm` implementing `render_layer`
2. register it in `converters/algorithms/__init__.py` (`_ALGORITHMS`,
   `_KINDS`, `_COMPLEXITY`)
3. declare its operator knobs via the `options_schema` ClassVar
4. add a unit test
5. bump the algorithms manifest version and regenerate the frontend
   snapshot (a CI drift gate enforces this)
6. mirror the option schema in `frontend/src/data/printRegistry.ts` so the
   editor renders the form and (optionally) offers a one-click style

If you want to add a *new file format*, see
[`docs/adding_a_converter.md`](../docs/adding_a_converter.md) instead.

## The contract

The base class lives in `backend/pen_plotter/converters/algorithms/base.py`:

```python
from typing import Any, ClassVar
from numpy.typing import NDArray
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm

class MyAlgorithm(RasterAlgorithm):
    name: ClassVar[str] = "my_algo"
    description: ClassVar[str] = "One-line operator-facing description."
    options_schema: ClassVar[list[OptionSpec]] = []   # see below
    tone_aware: ClassVar[bool] = False                # see below

    def render_layer(
        self,
        mask: NDArray[Any],          # bool array (height, width); True = region
        color_hex: str,              # layer colour, e.g. "#1a2b3c"
        label: str,                  # human-readable layer label
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        # return ONE SVG <g>...</g> group as a string
        ...
```

Key points:

- **One `<g>` per call.** The pipeline calls `render_layer` once per colour
  region and assembles the groups into the SVG pivot itself — you never emit
  an `<svg>` wrapper. Coordinates are in pixel space matching the source
  image (origin top-left).
- **Read knobs with `options.get(key, default)`** and clamp defensively —
  master styles inject extra internal keys (`angles`, `intensity`, `_tone`,
  `stroke_width`) that your algorithm should tolerate.
- **`tone_aware = True`** opts in to the per-pixel luminance map the render
  pipeline injects as `options["_tone"]` (a float array, same shape as the
  mask, 0 = black .. 1 = white). Use it to make dark areas denser — see
  `flowfield.py` or `voronoi_stipple.py` for the pattern. The pipeline only
  pays the dict-copy for algorithms that opt in.
- **Honour the pen width.** The frontend injects the physical pen tip width
  as `options["stroke_width"]` (SVG user units). Use the helpers in
  `converters/algorithms/_style.py` — `stroke_attr_px(opts)` for the group's
  `stroke-width` attribute and `floored_spacing(spacing, opts)` so hatch
  spacing never goes tighter than the pen tip.

## Option schema

`options_schema` is a list of `OptionSpec` (a frozen Pydantic model), the
single source of truth for the algorithm's tunables: the `/algorithms`
endpoint, the `/manifests/algorithms` JSON Schema (derived via
`OptionSpec.to_json_schema()`) and the frontend form all read from it.

```python
options_schema: ClassVar[list[OptionSpec]] = [
    OptionSpec(key="spacing_mm", label="convert.spacing", type="number",
               default=1.5, min=0.37, max=11, step=0.1),
    OptionSpec(key="mode", label="convert.mode", type="select",
               default="rows", choices=["rows", "columns"]),
    OptionSpec(key="seed", label="convert.seed", type="integer",
               default=0, min=0, step=1),
]
```

- `key` — the dict key you read via `options.get(key)`
- `label` — an i18n key the frontend runs through `t()`
- `type` — `number`, `integer`, `boolean`, `select` or `text`
- `default` / `min` / `max` / `step` — numeric envelope
- `choices` — allowed values for `select` knobs

Convention: geometry knobs are declared in **millimetres**
(`spacing_mm`, `cell_mm`, `dot_radius_mm`, `step_mm`, …) so the on-paper
pitch survives page-format changes. Algorithms still *read* the pixel
spelling (`options.get("spacing_px")`): the render pipeline converts
every `*_mm` option into its `*_px` twin at the placement's raster
scale before the algorithm runs (`convert_mm_options` in `_style.py`,
fed by the `target_width_mm`/`target_height_mm` the frontend ships with
each render). Raw `*_px` options remain accepted on the wire for saved
settings.

## A worked example — horizontal stripes

Modelled on the real `scanlines` / `moire` algorithms:

```python
# backend/pen_plotter/converters/algorithms/stripes.py
from __future__ import annotations

from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms._style import floored_spacing, stroke_attr_px
from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm


class StripesAlgorithm(RasterAlgorithm):
    """Horizontal stripes clipped to the mask."""

    name: ClassVar[str] = "stripes"
    description: ClassVar[str] = "Plain horizontal stripes clipped to the region."

    options_schema: ClassVar[list[OptionSpec]] = [
        # Declared in mm (UI contract); read below in px — the pipeline
        # converts spacing_mm → spacing_px at the placement scale.
        OptionSpec(key="spacing_mm", label="convert.spacing", type="number",
                   default=1.5, min=0.37, max=11, step=0.1),
    ]

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        opts = options or {}
        spacing = int(floored_spacing(max(1, int(opts.get("spacing_px", 4))), opts))
        bool_mask = mask.astype(bool)
        height, _width = bool_mask.shape

        parts: list[str] = []
        for y in range(0, height, spacing):
            row = bool_mask[y]
            if not row.any():
                continue
            # One <line> per on-mask run in this row.
            delta = np.diff(np.concatenate(([0], row.astype(np.int8), [0])))
            starts = np.flatnonzero(delta == 1)
            ends = np.flatnonzero(delta == -1)  # exclusive
            for a, b in zip(starts, ends, strict=True):
                if b - a >= 2:
                    parts.append(
                        f'<line x1="{a}" y1="{y}" x2="{b - 1}" y2="{y}"/>'
                    )

        return (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="{stroke_attr_px(opts):.3f}">'
            + "".join(parts)
            + "</g>"
        )
```

## Register it

All three dicts live in
`backend/pen_plotter/converters/algorithms/__init__.py`:

```python
from pen_plotter.converters.algorithms.stripes import StripesAlgorithm

_ALGORITHMS: dict[str, RasterAlgorithm] = {
    algo.name: algo
    for algo in (
        # … existing algorithms …
        StripesAlgorithm(),
    )
}

_KINDS["stripes"] = "lines"        # fill / lines / mono_stroke
_COMPLEXITY["stripes"] = "low"     # low / medium / high — preview cost hint
```

There is also `_HIDDEN`, a frozenset of algorithm names that stay registered
(persisted placements and presets keep rendering) but are not offered by the
editor's pickers for new layers — used to retire duplicates (e.g.
`tsp` → `tsp_opt`). You won't normally touch it for a new algorithm.

## Test

Tests feed a small synthetic mask and assert on the SVG group — see
`backend/tests/test_new_algorithms.py` for the house style:

```python
# backend/tests/test_stripes.py
import numpy as np

from pen_plotter.converters.algorithms.stripes import StripesAlgorithm


def _square_mask(size: int = 20, inset: int = 4) -> np.ndarray:
    mask = np.zeros((size, size), dtype=bool)
    mask[inset:-inset, inset:-inset] = True
    return mask


def test_stripes_emit_lines_for_filled_square() -> None:
    svg = StripesAlgorithm().render_layer(_square_mask(), "#000000", "layer 1")
    assert svg.startswith("<g")
    assert "<line" in svg


def test_empty_mask_yields_empty_group() -> None:
    mask = np.zeros((20, 20), dtype=bool)
    svg = StripesAlgorithm().render_layer(mask, "#000000", "layer 1")
    assert "<line" not in svg
```

Run the suite with `cd backend && uv run pytest`.

## Ship the contract changes

Recent algorithm batches all required these three steps — CI fails without
them:

1. **Bump the manifest version** — `ALGORITHMS_MANIFEST_VERSION` in
   `backend/pen_plotter/manifests/algorithms.py`. The manifest entry set
   changed (your new id), and the drift check
   (`backend/scripts/check_contracts.py`) forces a conscious bump.
2. **Regenerate the frontend snapshot** — `cd frontend && npm run
   gen:manifests` rewrites `frontend/src/domain/manifests/snapshot.json`
   (the offline fallback the manifest client bundles at build time). The
   same drift check compares the backend manifests against this snapshot,
   so a stale file fails CI.
3. **Mirror the schema in the print registry** —
   `frontend/src/data/printRegistry.ts`: add the id to the `AlgorithmId`
   union and an `AlgorithmSpec` entry (defaults + knob schema) to
   `ALGORITHMS`. To make the algorithm pickable in one click, also add a
   `PrintStyle` entry to `PRINT_STYLES` — `scope: 'layer'` for a per-layer
   preset, `scope: 'master'` if the style should own segmentation too.

## Editor recommendation (optional)

To have the Assistant wizard recommend your algorithm for some
(source, goal) pair, edit the recommendation matrix in
`backend/pen_plotter/domain/policy/rules.py` — `_MATRIX` maps
`(SourceKind, Goal)` to a `_BaseRule` (algorithm, quality tier, fallback
chain, options, optional multi-pass stack). Hard constraints live next door
in `constraints.py`. The HTTP surface (`POST /policy/resolve` in
`backend/pen_plotter/api/policy.py`) is a thin adapter over the pure
resolver — you never edit the API layer for a new rule.

## Front-end pickers (optional)

Algorithms surface in the editor through the print-style pickers, both
driven by `printRegistry.ts`:

- `frontend/src/components/edit/PrintStylePicker.vue` — per-layer styles on
  each layer card (featured short-list + "show all" long tail)
- `frontend/src/components/edit/render/MasterStylePicker.vue` — master
  style gallery on the Style tab (monochrome and multicolour families)

A new layer style shows up automatically once its `PRINT_STYLES` entry
exists; add its id to `FEATURED_LAYER_STYLE_IDS` in `PrintStylePicker.vue`
only if it deserves a spot in the curated short-list.

## See also

- [Picking the right algorithm](Picking-the-Right-Algorithm.md)
- [`docs/converters.md`](../docs/converters.md)
- [`docs/adding_a_converter.md`](../docs/adding_a_converter.md)
- [`docs/contract_architecture.md`](../docs/contract_architecture.md)
- [`docs/plugin-sdk.md`](../docs/plugin-sdk.md)
