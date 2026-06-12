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


def test_assigned_color_drives_mono_pen_swap_prompt() -> None:
    """``assigned_color_hex`` lands in the mono-pen-swap pause prompt.

    The operator-picked hex from the editor's per-layer picker replaces
    the raw cluster centroid in the ``; Change pen: ...`` comment, so
    the streamer's pop-up names the actual ink the operator owns
    instead of an arbitrary ``#a3b4c5`` mix.
    """
    profile = _profile().model_copy(update={"pen_slot_count": 1})  # mono-pen
    plan_red = LayerGeneration(
        layer_id="red",
        target_pen_slot=None,
        source_color="#a3b4c5",
        color_label=None,
        assigned_color_hex="#ff8800",
    )
    plan_blue = LayerGeneration(
        layer_id="blue",
        target_pen_slot=None,
        source_color="#112233",
        color_label=None,
        assigned_color_hex="#0044ff",
    )
    gcode = generate_gcode(TWO_LAYERS, profile, layers=[plan_red, plan_blue])
    # The pen-change comments name the assigned hexes, NOT the centroids.
    assert "; Change pen: #ff8800 (#ff8800)" in gcode
    assert "; Change pen: #0044ff (#0044ff)" in gcode
    assert "#a3b4c5" not in gcode
    assert "#112233" not in gcode


def test_assigned_color_promotes_to_tool_change_when_pen_installed() -> None:
    """When the operator's picked hex matches an installed pen, the
    G-code emits a proper tool-change instead of a mono-pen swap prompt.

    Lets the operator declare "this red layer goes on pen slot 3"
    implicitly: they pick the red hex, the backend matches it against
    the magazine, and the firmware gets a tool-change directive instead
    of a generic colour pop-up.
    """
    from pen_plotter.models import PenSlot

    profile = _profile().model_copy(
        update={
            "pen_slot_count": 2,
            "pens": [
                PenSlot(index=0, name="Black", color="#000000", installed=True),
                PenSlot(index=1, name="Red", color="#ff0000", installed=True),
            ],
        }
    )
    plan_red = LayerGeneration(
        layer_id="red",
        target_pen_slot=None,
        source_color="#abc123",
        color_label=None,
        assigned_color_hex="#ff0000",  # matches slot 1
    )
    plan_blue = LayerGeneration(
        layer_id="blue",
        target_pen_slot=None,
        source_color="#zzzzzz",  # ignored for the match
        color_label=None,
        assigned_color_hex="#000000",  # matches slot 0
    )
    gcode = generate_gcode(TWO_LAYERS, profile, layers=[plan_red, plan_blue])
    assert "; Change to pen slot 1 (Red)" in gcode
    assert "; Change to pen slot 0 (Black)" in gcode
    # Layer marker should reflect the promoted slot + assigned colour.
    assert "slot=1" in gcode
    assert "slot=0" in gcode


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


def test_generate_gcode_from_geometry_matches_svg_path() -> None:
    """The IR-based G-code generator produces equivalent output to the
    legacy SVG path on a round-tripped fixture (TODO 2.1 wire). Both
    paths share the same internal renderer; the IR variant just goes
    via ``_geometry_ir_to_svg`` first."""
    from pen_plotter.core.gcode import generate_gcode_from_geometry
    from pen_plotter.domain.ir.adapter import content_sha256, geometry_ir_from_svg

    profile = _profile()
    direct = generate_gcode(TWO_LAYERS, profile)
    ir = geometry_ir_from_svg(TWO_LAYERS, source_hash=content_sha256(b"x"))
    via_ir = generate_gcode_from_geometry(ir, profile)
    # Both paths should produce valid G-code with the same set of move
    # commands (the labels / comments may differ slightly because the
    # IR round-trip emits polylines instead of paths, but the resulting
    # G0/G1 stream is what drives the plotter).
    direct_moves = [ln for ln in direct.splitlines() if ln.startswith(("G0", "G1"))]
    via_ir_moves = [ln for ln in via_ir.splitlines() if ln.startswith(("G0", "G1"))]
    assert direct_moves, "legacy path must emit moves"
    assert via_ir_moves, "IR path must emit moves"
    # Equal move count: the geometry is preserved end to end.
    assert len(direct_moves) == len(via_ir_moves)


THREE_LAYERS = (
    f'<svg {NS} viewBox="0 0 100 100">'
    '<g inkscape:label="a" stroke="#ff0000"><path d="M10 10 L90 10"/></g>'
    '<g inkscape:label="b" stroke="#00ff00"><path d="M10 50 L90 50"/></g>'
    '<g inkscape:label="c" stroke="#0000ff"><path d="M10 90 L90 90"/></g>'
    "</svg>"
)


def _two_slot_profile():
    from pen_plotter.models import PenSlot

    return _profile().model_copy(
        update={
            "pen_slot_count": 2,
            "pens": [
                PenSlot(index=0, name="Black", color="#000000", installed=True),
                PenSlot(index=1, name="Red", color="#ff0000", installed=True),
            ],
        }
    )


def test_slot_reink_pause_names_the_wanted_ink() -> None:
    """Reusing a magazine slot with a different assigned colour pauses
    and prompts for the NEW ink — this is what lets an ink-loading plan
    cycle more colours than the magazine has slots.
    """
    gcode = generate_gcode(
        THREE_LAYERS,
        _two_slot_profile(),
        layers=[
            LayerGeneration(layer_id="a", target_pen_slot=0, assigned_color_hex="#000000"),
            LayerGeneration(layer_id="b", target_pen_slot=1, assigned_color_hex="#ff0000"),
            LayerGeneration(
                layer_id="c",
                target_pen_slot=0,
                assigned_color_hex="#00ff00",
                color_label="Vert prairie",
            ),
        ],
    )
    # First two layers use the mounted pens — prompts carry the profile names.
    assert "; Change to pen slot 0 (Black)" in gcode
    assert "; Change to pen slot 1 (Red)" in gcode
    # Third layer re-inks slot 0: the prompt names the wanted ink (label
    # + hex so the UI can render a swatch), not the pen that used to
    # live there.
    assert "; Change to pen slot 0 (Vert prairie #00ff00)" in gcode


def test_consecutive_same_slot_reink_still_pauses() -> None:
    """Two consecutive layers on the SAME slot with different assigned
    colours must pause between them (slot unchanged, ink changed)."""
    gcode = generate_gcode(
        TWO_LAYERS,
        _two_slot_profile(),
        layers=[
            LayerGeneration(layer_id="red", target_pen_slot=0, assigned_color_hex="#000000"),
            LayerGeneration(layer_id="blue", target_pen_slot=0, assigned_color_hex="#00aaff"),
        ],
    )
    assert "; Change to pen slot 0 (Black)" in gcode
    assert "; Change to pen slot 0 (#00aaff)" in gcode


def test_same_slot_same_ink_does_not_reink_pause() -> None:
    """Re-using the slot with the SAME ink stays pause-free (auto)."""
    gcode = generate_gcode(
        TWO_LAYERS,
        _two_slot_profile(),
        layers=[
            LayerGeneration(layer_id="red", target_pen_slot=0, assigned_color_hex="#000000"),
            LayerGeneration(layer_id="blue", target_pen_slot=0, assigned_color_hex="#000000"),
        ],
    )
    assert gcode.count("; Change to pen slot 0") == 1


def test_magazine_reink_pauses_for_operator_load() -> None:
    """Carousel/rack magazines can't fetch an ink that isn't physically
    loaded: a re-ink boundary (slot reused with a different colour) must
    emit an operator LOAD pause, not the automated firmware/host swap —
    that swap would silently keep drawing with the old ink.
    """
    for method in ("carousel", "rack"):
        profile = _two_slot_profile().model_copy(
            update={"tool_change_method": method, "capabilities": None}
        )
        gcode = generate_gcode(
            TWO_LAYERS,
            profile,
            layers=[
                LayerGeneration(layer_id="red", target_pen_slot=0, assigned_color_hex="#000000"),
                LayerGeneration(
                    layer_id="blue",
                    target_pen_slot=0,
                    assigned_color_hex="#00aaff",
                    color_label="Bleu ciel",
                ),
            ],
        )
        assert "Load pen slot 0 (Bleu ciel #00aaff) into magazine" in gcode, method
        assert "; Change to pen slot 0 (Bleu ciel" not in gcode, method


def test_guided_swap_actions_reink_is_operator_confirm_on_carousel() -> None:
    """At stream time the re-ink load boundary halts for the operator
    even on an automated magazine, while the regular first-use swap
    stays an automated firmware action.
    """
    from pen_plotter.core.toolchange import guided_swap_actions

    profile = _two_slot_profile().model_copy(
        update={
            "tool_change_method": "carousel",
            "tool_change_command": "M6 T{slot}",
            "capabilities": None,
        }
    )
    gcode = generate_gcode(
        TWO_LAYERS,
        profile,
        layers=[
            LayerGeneration(layer_id="red", target_pen_slot=0, assigned_color_hex="#000000"),
            LayerGeneration(
                layer_id="blue",
                target_pen_slot=0,
                assigned_color_hex="#00aaff",
                color_label="Bleu ciel",
            ),
        ],
    )
    actions = list(guided_swap_actions(gcode, profile).values())
    assert len(actions) == 2
    first, reink = actions
    # First use of slot 0: the carousel swaps by itself, with the slot
    # substituted into the firmware trigger.
    assert first.kind == "firmware"
    assert [c.send for c in first.commands] == ["M6 T0"]
    # Re-ink: operator pause naming the ink to load.
    assert reink.kind == "operator_confirm"
    assert "Bleu ciel #00aaff" in (reink.prompt or "")
    assert "slot 0" in (reink.prompt or "")


def test_misconfigured_rack_degrades_to_operator_pause() -> None:
    """A rack/host profile with NO authored swap sequence used to make
    ``guided_swap_actions`` raise at enqueue (opaque 500). It must
    degrade to a manual operator pause so the run stays printable."""
    from pen_plotter.core.toolchange import guided_swap_actions
    from pen_plotter.domain.capability import derive_capabilities

    caps = derive_capabilities("rack", 2)
    caps.tool_change.host_swap = None
    caps.tool_change.host_macro = []
    profile = _two_slot_profile().model_copy(
        update={"tool_change_method": "rack", "capabilities": caps}
    )
    gcode = generate_gcode(
        TWO_LAYERS,
        profile,
        layers=[
            LayerGeneration(layer_id="red", target_pen_slot=0),
            LayerGeneration(layer_id="blue", target_pen_slot=1),
        ],
    )
    actions = list(guided_swap_actions(gcode, profile).values())
    assert len(actions) == 2
    assert all(a.kind == "operator_confirm" for a in actions)
    assert "swap by hand" in (actions[0].prompt or "")
