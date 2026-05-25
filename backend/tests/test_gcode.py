import pytest

from pen_plotter.core.gcode import LayerGeneration, generate_gcode
from pen_plotter.profiles import get_profile

NS = (
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
)
TWO_LAYERS = (
    f'<svg {NS} viewBox="0 0 100 100">'
    '<g inkscape:label="red" stroke="#ff0000"><path d="M10 10 L90 10 L90 90"/></g>'
    '<g inkscape:label="blue" stroke="#0000ff"><path d="M10 50 L90 50"/></g>'
    "</svg>"
)


def _profile():
    profile = get_profile("Custom CoreXY A3")
    assert profile is not None
    return profile


def test_generates_header_pen_and_footer() -> None:
    gcode = generate_gcode(TWO_LAYERS, _profile())
    assert "G21" in gcode  # mm units
    assert "G90" in gcode  # absolute
    assert "M280 P0 S40" in gcode  # pen up command from profile
    assert "M280 P0 S90" in gcode  # pen down command
    assert "G1 X" in gcode
    assert gcode.strip().endswith("M2")  # grbl end


def test_fits_within_workspace() -> None:
    profile = _profile()
    gcode = generate_gcode(TWO_LAYERS, profile, scale_mode="fit", margin_mm=10)
    xs, ys = [], []
    for line in gcode.splitlines():
        if line.startswith(("G0", "G1")):
            for token in line.split():
                if token.startswith("X"):
                    xs.append(float(token[1:]))
                elif token.startswith("Y"):
                    ys.append(float(token[1:]))
    assert min(xs) >= profile.workspace.x_min - 0.01
    assert max(xs) <= profile.workspace.x_max + 0.01
    assert min(ys) >= profile.workspace.y_min - 0.01
    assert max(ys) <= profile.workspace.y_max + 0.01


def test_tool_change_emitted_for_pen_slots() -> None:
    gcode = generate_gcode(
        TWO_LAYERS,
        _profile(),
        layers=[
            LayerGeneration(layer_id="red", target_pen_slot=0),
            LayerGeneration(layer_id="blue", target_pen_slot=3),
        ],
    )
    assert "Change to pen slot 0" in gcode
    assert "Change to pen slot 3" in gcode
    assert "M0" in gcode


def test_per_slot_pen_command_override() -> None:
    from pen_plotter.models import PenSlot

    profile = _profile().model_copy(
        update={
            "pens": [
                PenSlot(index=0, name="Deep", installed=True, pen_down_command="M280 P0 S110"),
            ]
        }
    )
    gcode = generate_gcode(
        TWO_LAYERS,
        profile,
        layers=[LayerGeneration(layer_id="red", target_pen_slot=0)],
    )
    # The slot-0 layer uses its calibrated pen-down command...
    assert "M280 P0 S110" in gcode
    # ...while the unassigned "blue" layer keeps the profile default.
    assert "M280 P0 S90" in gcode


def test_tool_change_uses_configured_pen_name_and_warns_when_absent() -> None:
    from pen_plotter.models import PenSlot

    profile = _profile()
    profile = profile.model_copy(
        update={
            "pens": [
                PenSlot(index=0, name="Black 0.3", installed=True),
                PenSlot(index=3, name="Red 0.5", installed=False),
            ]
        }
    )
    gcode = generate_gcode(
        TWO_LAYERS,
        profile,
        layers=[
            LayerGeneration(layer_id="red", target_pen_slot=0),
            LayerGeneration(layer_id="blue", target_pen_slot=3),
        ],
    )
    assert "Black 0.3" in gcode
    assert "Red 0.5" in gcode
    assert "pen slot 3 is not installed" in gcode


def test_tool_change_warns_when_target_slot_absent_from_magazine() -> None:
    from pen_plotter.models import PenSlot

    profile = _profile().model_copy(
        update={"pens": [PenSlot(index=0, name="Black", installed=True)]}
    )
    gcode = generate_gcode(
        TWO_LAYERS,
        profile,
        layers=[
            LayerGeneration(layer_id="red", target_pen_slot=0),
            LayerGeneration(layer_id="blue", target_pen_slot=2),
        ],
    )
    assert "pen slot 2 is not installed" in gcode


def test_effective_pens_derives_defaults_when_unset() -> None:
    pens = _profile().effective_pens()
    assert len(pens) == 6
    assert pens[0].index == 0
    assert pens[0].installed is True


def test_layer_speed_override_sets_feed() -> None:
    gcode = generate_gcode(
        TWO_LAYERS,
        _profile(),
        layers=[LayerGeneration(layer_id="red", drawing_speed_mm_s=10.0)],
    )
    assert "F600.0" in gcode  # 10 mm/s * 60


def test_invalid_svg_raises() -> None:
    with pytest.raises(ValueError):
        generate_gcode("<svg><g></svg>", _profile())


def test_travel_moves_carry_profile_feedrate() -> None:
    """Rapid moves must explicitly set F=travel_speed*60 — firmwares otherwise
    keep the previous F, which makes pen-up travel match drawing speed.
    """
    profile = _profile()
    gcode = generate_gcode(TWO_LAYERS, profile)
    travel_lines = [line for line in gcode.splitlines() if line.startswith("G0 ")]
    assert travel_lines, "no G0 travel moves were emitted"
    expected_feed = f"F{profile.travel_speed_mm_s * 60.0:.1f}"
    for line in travel_lines:
        assert expected_feed in line, f"travel line missing {expected_feed}: {line}"


def test_acceleration_emitted_for_standard_dialects() -> None:
    """M204 must appear once in the header for grbl/marlin/klipper profiles
    with a non-zero acceleration. Firmwares otherwise use their compiled
    default, ignoring the operator's profile value.
    """
    profile = _profile()
    assert profile.gcode_dialect == "grbl"
    gcode = generate_gcode(TWO_LAYERS, profile)
    expected = f"M204 S{profile.acceleration_mm_s2:.1f}"
    assert gcode.count(expected) == 1, gcode


def test_acceleration_skipped_when_zero() -> None:
    """A profile with acceleration=0 must NOT emit M204 (the zero would
    paradoxically tell the firmware to stop accelerating).
    """
    profile = _profile().model_copy(update={"acceleration_mm_s2": 0.0})
    gcode = generate_gcode(TWO_LAYERS, profile)
    assert "M204" not in gcode


def test_acceleration_skipped_for_custom_dialect() -> None:
    """``custom`` and ``ebb`` dialects must not get M204 — they have their
    own acceleration mechanism (or none at all).
    """
    profile = _profile().model_copy(update={"gcode_dialect": "custom"})
    gcode = generate_gcode(TWO_LAYERS, profile)
    assert "M204" not in gcode


def test_template_contract_blocks_undeclared_variable_at_import() -> None:
    """A template growing a ``{{ feed }}`` reference that ``generate_gcode``
    doesn't pass must fail loudly — at module import time — rather than
    silently returning a 422 ``'feed' is undefined`` on the next
    /generate call.

    This is the defence against deployment desync: stale ``__pycache__``
    next to fresh templates (or vice versa) used to surface as the
    opaque ``Generation failed: 'feed' is undefined`` error reported by
    operators. With the boot-time check in place the failure happens
    once at startup, in the uvicorn log, naming the offending template +
    variable.
    """
    import importlib

    from pen_plotter.core import gcode as gcode_module

    # Pen-up.j2 today only uses ``profile``. Pretend it grew a new
    # ``{{ feed }}`` reference and verify the contract rejects it.
    template_path = gcode_module._TEMPLATES_DIR / "pen_up.j2"
    original = template_path.read_text()
    template_path.write_text(original + "\nF{{ feed }}\n")
    try:
        with pytest.raises(RuntimeError, match=r"pen_up\.j2.*feed"):
            importlib.reload(gcode_module)
    finally:
        template_path.write_text(original)
        # Restore the canonical module so subsequent tests see the real
        # ``generate_gcode`` rather than the half-reloaded broken state.
        importlib.reload(gcode_module)
