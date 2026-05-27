# Plugin SDK

Roadmap step **D.8**. Stable import surface for writing third-party
extensions against OmniPlot v0.2.

> Today plugins ship by adding code to the bundled registries. The
> SDK formalises the **types** an external plugin keys on, so the
> code you write now doesn't need a rewrite when entry-point
> discovery lands.

## Import surface

All third-party plugin code imports from `pen_plotter.sdk`. The
underlying modules may move; the SDK module is stable.

```python
from pen_plotter.sdk import (
    RasterAlgorithm,            # new raster algorithms
    Converter, ConversionResult,# new file-format converters
    ToolChangeStrategyImpl,     # new tool-change modes
    SwapPlan, SwapContext,      # tool-change events
    MachineProfile,             # operator-shipped profiles
    PluginManifest,             # new manifest domains
    register_manifest,          # register a domain provider
)
```

Stability: changes follow the **manifest deprecation window** —
max(2 manifest versions, 2 months) per
`docs/contract_architecture.md`.

## Example 1 — Raster algorithm

A minimal "checker" algorithm that fills a layer with a checkerboard
pattern. Drop this in your project and register it in your bootstrap.

```python
from numpy.typing import NDArray
import numpy as np
from pen_plotter.sdk import RasterAlgorithm
from pen_plotter.converters.algorithms import _ALGORITHMS  # (1)

class CheckerAlgorithm(RasterAlgorithm):
    name = "checker"
    description = "Fill the layer with a checkerboard pattern."

    def render_layer(
        self,
        mask: NDArray[np.bool_],
        color: str,
        label: str,
        *,
        options: dict | None = None,
    ) -> str:
        # ... emit an SVG <g> string ...
        return f'<g inkscape:label="{label}" stroke="{color}"></g>'

# (1) For v0.2: hook into the existing registry directly.
#     Phase B follow-up: ``register_manifest('algorithms', ...)`` will
#     accept third-party entries declaratively.
_ALGORITHMS[CheckerAlgorithm().name] = CheckerAlgorithm()
```

The algorithm becomes available immediately at `/manifests/algorithms`
and through the bitmap converter.

## Example 2 — Tool-change strategy

A new mode for a robot arm that hands the pen back to a CNC tool
changer. The strategy subclasses
`pen_plotter.sdk.ToolChangeStrategyImpl` (the abstract one).

```python
from pen_plotter.sdk import (
    ToolChangeStrategyImpl,
    ToolingMode,
    SwapContext,
    SwapPlan,
    SwapCommand,
    PauseKind,
    MachineCapabilities,
)

class RoboticArmStrategy(ToolChangeStrategyImpl):
    mode = ToolingMode.HOST_MACRO  # reuse an existing mode

    def plan(self, context: SwapContext, capabilities: MachineCapabilities) -> SwapPlan:
        return SwapPlan(
            mode=self.mode,
            pause_kind=PauseKind.HOST_TIMED,
            commands=[
                SwapCommand(send=f"; robot handoff for slot {context.slot_index}"),
                SwapCommand(send=f"ARM_PICK {context.slot_index}", wait_ms=1500),
                SwapCommand(send="ARM_PLACE", wait_ms=1500),
            ],
            recovery_policy=capabilities.tool_change.recovery_policy,
        )
```

Register in your bootstrap (until the manifest-based registration
lands):

```python
from pen_plotter.domain.toolchange.strategies import _STRATEGIES
_STRATEGIES[ToolingMode.HOST_MACRO] = RoboticArmStrategy  # (1)
```

> (1) Replaces the default `HostMacroStrategy` for your deployment.
> Future entry-point discovery will let multiple strategies coexist
> per mode and let the profile pick.

## Example 3 — Machine profile

The simplest plugin: a YAML file. Drop it under
`$OMNIPLOT_PROFILES_DIR/` and the v0.2 Capability Model (A.5)
validates it on load. Schema is in `docs/profile_format.md`.

```yaml
name: "My Custom Plotter"
units: "mm"
workspace: { x_min: 0, y_min: 0, x_max: 297, y_max: 210 }
origin: "bottom_left"
gcode_dialect: "grbl"
pen_up_command: "M03 S60"
pen_down_command: "M03 S130"
tool_change_method: "manual_pause"
tool_change_command: "M0"
drawing_speed_mm_s: 45.0
travel_speed_mm_s: 90.0
acceleration_mm_s2: 800.0
pen_slot_count: 4
capabilities:
  tool_change:
    mode: manual
    command_source: operator
    recovery_policy: pause_and_prompt
    manual_prompt:
      title: "Change pen"
      body: "Insert pen {color}, then press Resume."
  max_pens_in_magazine: 4
```

## Example 4 — Manifest domain

A plugin that exposes its own data through the manifest envelope.

```python
from pen_plotter.sdk import (
    ManifestEntry, ManifestMeta, PluginManifest, register_manifest,
)

class StyleManifestEntry(ManifestEntry):
    label: str
    swatch: str  # CSS colour

def my_styles() -> PluginManifest[StyleManifestEntry]:
    return PluginManifest[StyleManifestEntry](
        meta=ManifestMeta(
            domain="custom.styles",
            manifest_version=1,
        ),
        entries=[
            StyleManifestEntry(id="ink_drawing", label="Ink Drawing", swatch="#222"),
            StyleManifestEntry(id="pencil",      label="Pencil",      swatch="#888"),
        ],
    )

register_manifest("custom.styles", my_styles)
```

Once registered, `GET /manifests/custom.styles` serves the payload,
the frontend zod fallback chain (A.7) treats it like any other
domain, and the contract check (D.5) verifies its snapshot.

## Roadmap for plugins

- **Now:** import from `pen_plotter.sdk`, register into the bundled
  in-process registries.
- **Phase B follow-up:** discovery via Python entry points
  (`pyproject.toml [project.entry-points.\"omniplot.algorithms\"]`).
  The SDK module stays the same; the bootstrap that calls
  `register_*` becomes automatic.
- **V2:** signed plugin manifests + a marketplace (audit #1 phase 4).
