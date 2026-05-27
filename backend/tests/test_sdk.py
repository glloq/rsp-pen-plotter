"""Smoke tests for the plugin SDK surface (roadmap D.8).

These tests pretend to be a third-party plugin author: they import
**only** from ``pen_plotter.sdk`` and exercise enough of the API to
catch a future refactor that breaks the published surface.
"""

from __future__ import annotations

import inspect

import numpy as np
from numpy.typing import NDArray

import pen_plotter.sdk as sdk


def test_sdk_exports_the_documented_surface() -> None:
    expected = {
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
    }
    assert set(sdk.__all__) == expected, "sdk.__all__ drifted from docs"


def test_third_party_raster_algorithm_can_subclass_via_sdk() -> None:
    """A plugin author should never have to import from converters.algorithms.base."""

    class Demo(sdk.RasterAlgorithm):
        name = "demo_sdk"
        description = "Demo raster algorithm for the SDK test."

        def render_layer(
            self,
            mask: NDArray[np.bool_],  # noqa: ARG002 — required signature
            color: str,
            label: str,
            *,
            options: dict | None = None,  # noqa: ARG002
        ) -> str:
            return f'<g inkscape:label="{label}" stroke="{color}"/>'

    algo = Demo()
    out = algo.render_layer(np.zeros((4, 4), dtype=np.bool_), "#000", "l1", options={})
    assert "<g" in out
    # The base class is the same as the bundled one (no shadow type).
    from pen_plotter.converters.algorithms.base import RasterAlgorithm as Internal

    assert sdk.RasterAlgorithm is Internal


def test_plugin_manifest_alias_matches_manifest() -> None:
    assert sdk.PluginManifest is sdk.Manifest


def test_plugin_can_register_a_custom_domain() -> None:
    """Manifest registration through the SDK surface works."""

    class _Entry(sdk.ManifestEntry):
        label: str

    def _provider() -> sdk.PluginManifest[_Entry]:
        return sdk.PluginManifest[_Entry](
            meta=sdk.ManifestMeta(domain="sdk.test", manifest_version=1),
            entries=[_Entry(id="alpha", label="Alpha")],
        )

    sdk.register_manifest("sdk.test", _provider)
    from pen_plotter.manifests import get_manifest

    m = get_manifest("sdk.test")
    assert m.meta.domain == "sdk.test"
    assert m.entries[0].id == "alpha"  # type: ignore[attr-defined]


def test_tool_change_strategy_impl_is_subclassable() -> None:
    """A third-party tool-change strategy can subclass ToolChangeStrategyImpl."""

    class _Demo(sdk.ToolChangeStrategyImpl):
        mode = sdk.ToolingMode.HOST_MACRO

        def plan(
            self, context: sdk.SwapContext, capabilities: sdk.MachineCapabilities
        ) -> sdk.SwapPlan:
            return sdk.SwapPlan(
                mode=self.mode,
                pause_kind=sdk.PauseKind.HOST_TIMED,
                commands=[sdk.SwapCommand(send="; demo")],
                recovery_policy=capabilities.tool_change.recovery_policy,
            )

    # The base requires a profile in its __init__.
    sig = inspect.signature(sdk.ToolChangeStrategyImpl.__init__)
    assert "profile" in sig.parameters


def test_machine_profile_is_exported_and_validates() -> None:
    payload = {
        "name": "Sdk Test",
        "units": "mm",
        "workspace": {"x_min": 0, "y_min": 0, "x_max": 100, "y_max": 100},
        "origin": "top_left",
        "gcode_dialect": "grbl",
        "pen_up_command": "G0 Z5",
        "pen_down_command": "G0 Z0",
        "tool_change_method": "manual_pause",
        "tool_change_command": "M0",
        "drawing_speed_mm_s": 50.0,
        "travel_speed_mm_s": 100.0,
        "acceleration_mm_s2": 1000.0,
        "pen_slot_count": 1,
    }
    profile = sdk.MachineProfile.model_validate(payload)
    assert profile.name == "Sdk Test"
    # Capability Model derivation still works through the SDK import.
    caps = profile.effective_capabilities()
    assert caps.tool_change.mode is sdk.ToolingMode.MANUAL
