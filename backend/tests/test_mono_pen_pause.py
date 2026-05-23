"""Tests for mono-pen colour-change pauses in the G-code generator.

The default tool-change loop in :func:`generate_gcode` only emits a pause
when ``target_pen_slot`` changes. For mono-pen machines we surface a
*colour-change* prompt instead, driven by ``LayerInfo.source_color`` and
``pause_before``. These tests pin that behaviour and confirm the legacy
slot-change path still works alongside it.
"""

from __future__ import annotations

from pen_plotter.core.gcode import LayerGeneration, generate_gcode
from pen_plotter.core.toolchange import guided_pause_points
from pen_plotter.models import MachineProfile
from pen_plotter.profiles import get_profile

NS = (
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
)
THREE_COLOURS = (
    f'<svg {NS} viewBox="0 0 100 100">'
    '<g inkscape:label="red"><path d="M10 10 L90 10"/></g>'
    '<g inkscape:label="green"><path d="M10 50 L90 50"/></g>'
    '<g inkscape:label="blue"><path d="M10 90 L90 90"/></g>'
    "</svg>"
)


def _mono_pen_profile() -> MachineProfile:
    """Borrow a GRBL profile and set ``pen_slot_count=1`` for mono-pen tests."""
    base = get_profile("Custom CoreXY A3")
    assert base is not None
    return base.model_copy(update={"pen_slot_count": 1, "pens": None})


def test_three_distinct_colours_emit_three_prompts() -> None:
    """Mono-pen + 3 colours = initial install + 2 swaps = 3 prompts total."""
    profile = _mono_pen_profile()
    gcode = generate_gcode(
        THREE_COLOURS,
        profile,
        layers=[
            LayerGeneration(layer_id="red", source_color="#ff0000", color_label="Red"),
            LayerGeneration(layer_id="green", source_color="#00ff00", color_label="Green"),
            LayerGeneration(layer_id="blue", source_color="#0000ff", color_label="Blue"),
        ],
    )
    points = guided_pause_points(gcode, profile)
    assert len(points) == 3
    prompts = list(points.values())
    assert "Red" in prompts[0]
    assert "Green" in prompts[1]
    assert "Blue" in prompts[2]
    # Each prompt carries the hex colour as well.
    assert "#ff0000" in prompts[0]


def test_same_colour_runs_emit_one_initial_prompt() -> None:
    """Consecutive layers of the same colour share a pen, only initial pause."""
    profile = _mono_pen_profile()
    gcode = generate_gcode(
        THREE_COLOURS,
        profile,
        layers=[
            LayerGeneration(layer_id="red", source_color="#ff0000"),
            LayerGeneration(layer_id="green", source_color="#ff0000"),
            LayerGeneration(layer_id="blue", source_color="#ff0000"),
        ],
    )
    assert len(guided_pause_points(gcode, profile)) == 1


def test_pause_before_never_skips_swap() -> None:
    """A layer with ``pause_before='never'`` does not emit a prompt."""
    profile = _mono_pen_profile()
    gcode = generate_gcode(
        THREE_COLOURS,
        profile,
        layers=[
            LayerGeneration(layer_id="red", source_color="#ff0000"),
            LayerGeneration(layer_id="green", source_color="#00ff00", pause_before="never"),
            LayerGeneration(layer_id="blue", source_color="#0000ff"),
        ],
    )
    points = guided_pause_points(gcode, profile)
    # Initial install + skip on green + swap before blue = 2 prompts.
    assert len(points) == 2
    prompts = list(points.values())
    assert "#ff0000" in prompts[0]
    assert "#0000ff" in prompts[1]


def test_pause_before_always_forces_swap_on_same_colour() -> None:
    """``pause_before='always'`` injects a prompt even with no colour change."""
    profile = _mono_pen_profile()
    gcode = generate_gcode(
        THREE_COLOURS,
        profile,
        layers=[
            LayerGeneration(layer_id="red", source_color="#ff0000"),
            LayerGeneration(layer_id="green", source_color="#ff0000", pause_before="always"),
            LayerGeneration(layer_id="blue", source_color="#ff0000"),
        ],
    )
    # Initial + forced = 2 prompts (the third layer stays on the same colour).
    assert len(guided_pause_points(gcode, profile)) == 2


def test_label_fallback_to_hex_when_unset() -> None:
    """No ``color_label`` -> the prompt uses the hex colour directly."""
    profile = _mono_pen_profile()
    gcode = generate_gcode(
        THREE_COLOURS,
        profile,
        layers=[
            LayerGeneration(layer_id="red", source_color="#ff0000"),
        ],
    )
    points = guided_pause_points(gcode, profile)
    assert len(points) == 1
    # When the label equals the hex, the prompt collapses to "Change pen to #hex".
    prompt = next(iter(points.values()))
    assert prompt == "Change pen to #ff0000"


def test_legacy_slot_format_still_parses() -> None:
    """Old G-code with ``; Change to pen slot N`` keeps producing prompts."""
    profile = get_profile("Custom CoreXY A3")
    assert profile is not None
    legacy_gcode = (
        "G21\n"
        "G90\n"
        "; Change to pen slot 0 (Pen 0)\n"
        "M0\n"
        "G0 X10 Y10\n"
        "; Change to pen slot 3 (Pen 3)\n"
        "M0\n"
        "G1 X20 Y20 F600\n"
    )
    points = guided_pause_points(legacy_gcode, profile)
    assert len(points) == 2
    assert all(prompt.startswith("Insert pen slot") for prompt in points.values())
