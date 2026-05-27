"""Plugin SDK — public surface for third-party extensions (roadmap D.8).

Audit #1 §1 + #1 § plugin layer call out the v0.2 goal of letting an
external developer write a plugin (a new raster algorithm, a new
machine profile, a new tool-change strategy) without depending on
internal modules. This package is the **stable import surface**.

Today plugins are loaded by **adding code to the bundled
registries** — there is no entry-point discovery yet. The SDK
formalises the **types and contracts** a future entry-point loader
will key on, so writing a plugin against this surface today doesn't
need a rewrite when discovery lands. See ``docs/plugin-sdk.md``.

Public types exported from this module:

- :class:`RasterAlgorithm` — base class for new raster algorithms.
- :class:`Converter` / :class:`ConversionResult` — bytes → SVG converters.
- :class:`ToolChangeStrategy` (the abstract one from
  :mod:`pen_plotter.domain.toolchange.strategies`) — new tool-change
  modes register through this.
- :class:`MachineProfile` — operators ship a profile as a YAML file
  validated against this Pydantic model.
- :class:`PluginManifest` (aliased to :class:`Manifest`) — third-party
  domains register through the manifest system.

Stability promise: this module follows the same deprecation policy
as the manifest envelope (``max(2 manifest versions, 2 months)``)
per ``docs/contract_architecture.md``.
"""

from __future__ import annotations

# Algorithm plugins
from pen_plotter.converters.algorithms.base import RasterAlgorithm

# Converter plugins
from pen_plotter.converters.base import (
    ConversionResult,
    Converter,
    UnsupportedFormatError,
)
from pen_plotter.converters.registry import registry as converter_registry

# Tool-change strategy plugins
from pen_plotter.domain.capability import (
    CommandSource,
    HostMacroStep,
    MachineCapabilities,
    ManualSwapPrompt,
    RecoveryPolicy,
    ToolChangeStrategy,
    ToolingMode,
)
from pen_plotter.domain.toolchange.orchestrator import (
    PauseKind,
    SwapCommand,
    SwapContext,
    SwapPlan,
)
from pen_plotter.domain.toolchange.strategies import (
    ToolChangeStrategy as ToolChangeStrategyImpl,
)
from pen_plotter.manifests import (
    Manifest,
    ManifestEntry,
    ManifestMeta,
    register_manifest,
)
from pen_plotter.models import MachineProfile, PenSlot, WorkspaceBounds

# Convenience alias — third-party developers see PluginManifest in
# their imports; internally it's the same Manifest type.
PluginManifest = Manifest

__all__ = [
    "CommandSource",
    "ConversionResult",
    "Converter",
    "HostMacroStep",
    "MachineCapabilities",
    "MachineProfile",
    "Manifest",
    "ManifestEntry",
    "ManifestMeta",
    "ManualSwapPrompt",
    "PauseKind",
    "PenSlot",
    "PluginManifest",
    "RasterAlgorithm",
    "RecoveryPolicy",
    "SwapCommand",
    "SwapContext",
    "SwapPlan",
    "ToolChangeStrategy",
    "ToolChangeStrategyImpl",
    "ToolingMode",
    "UnsupportedFormatError",
    "WorkspaceBounds",
    "converter_registry",
    "register_manifest",
]
