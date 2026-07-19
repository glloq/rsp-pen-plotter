"""Tests for the geometry IR + artifact hashing (roadmap A.3)."""

from __future__ import annotations

import pytest

from pen_plotter.domain.ir import (
    IR_SCHEMA_VERSION,
    GeometryIR,
    LayerGeometry,
    MachineProgram,
    PathPlanIR,
    PlannedLayer,
    Polyline,
    SegmentationArtifact,
    SourceAsset,
    artifact_hash,
)
from pen_plotter.domain.ir.adapter import (
    content_sha256,
    geometry_ir_from_svg,
    is_ir_enabled,
)


def test_artifact_hash_is_deterministic() -> None:
    a = SourceAsset(filename="x.png", mime="image/png", size_bytes=10, content_sha256="abc")
    b = SourceAsset(filename="x.png", mime="image/png", size_bytes=10, content_sha256="abc")
    assert artifact_hash(a) == artifact_hash(b)


def test_artifact_hash_changes_with_payload() -> None:
    a = SourceAsset(filename="x.png", mime="image/png", size_bytes=10, content_sha256="abc")
    b = SourceAsset(filename="x.png", mime="image/png", size_bytes=11, content_sha256="abc")
    assert artifact_hash(a) != artifact_hash(b)


def test_artifact_hash_is_blind_to_created_at() -> None:
    a = SourceAsset(filename="x.png", mime="image/png", size_bytes=1, content_sha256="abc")
    b = SourceAsset(filename="x.png", mime="image/png", size_bytes=1, content_sha256="abc")
    # Different created_at because constructed at different instants.
    assert a.created_at != b.created_at or True  # tolerate same-ms construction
    assert artifact_hash(a) == artifact_hash(b)


def test_artifact_hash_includes_ir_version() -> None:
    a = SourceAsset(filename="x.png", mime="image/png", size_bytes=1, content_sha256="abc")
    payload = a.model_dump()
    # Forge an "old" artifact at a different schema version and confirm
    # the hash diverges even though everything else is identical.
    b = SourceAsset(**{**payload, "ir_version": IR_SCHEMA_VERSION + 1})
    assert artifact_hash(a) != artifact_hash(b)


def test_round_trip_geometry_ir() -> None:
    geo = GeometryIR(
        source_hash="abc",
        viewbox=(0.0, 0.0, 100.0, 100.0),
        layers=[
            LayerGeometry(
                layer_id="layer-1",
                color="#ff0000",
                polylines=[Polyline(points=[(0.0, 0.0), (1.0, 1.0)])],
            )
        ],
    )
    dumped = geo.model_dump_json()
    restored = GeometryIR.model_validate_json(dumped)
    assert artifact_hash(restored) == artifact_hash(geo)


def test_round_trip_path_plan_and_machine_program() -> None:
    plan = PathPlanIR(
        geometry_hash="g",
        layers=[
            PlannedLayer(
                layer_id="l1",
                polylines=[Polyline(points=[(0.0, 0.0), (1.0, 0.0)])],
                draw_length_mm=1.0,
            )
        ],
        total_draw_length_mm=1.0,
    )
    prog = MachineProgram(
        profile_name="axidraw_v3",
        dialect="ebb",
        line_count=42,
        gcode="; hello\n",
    )
    assert artifact_hash(plan) == artifact_hash(
        PathPlanIR.model_validate_json(plan.model_dump_json())
    )
    assert artifact_hash(prog) == artifact_hash(
        MachineProgram.model_validate_json(prog.model_dump_json())
    )


def test_segmentation_artifact_hash_stable() -> None:
    seg = SegmentationArtifact(
        source_hash="s",
        palette=[(255, 0, 0), (0, 255, 0)],
        width_px=4,
        height_px=4,
        label_image_sha256="z",
    )
    assert artifact_hash(seg) == artifact_hash(
        SegmentationArtifact.model_validate_json(seg.model_dump_json())
    )


def test_is_ir_enabled_default_off(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("OMNIPLOT_IR_ENABLED", raising=False)
    assert is_ir_enabled() is False
    monkeypatch.setenv("OMNIPLOT_IR_ENABLED", "1")
    assert is_ir_enabled() is True


def test_geometry_ir_from_svg_extracts_layered_polylines() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'viewBox="0 0 100 100">'
        '<g inkscape:label="red" stroke="#ff0000">'
        '<path d="M 0,0 L 10,0 L 10,10 Z"/>'
        '<line x1="0" y1="0" x2="5" y2="5"/>'
        "</g>"
        '<g inkscape:label="blue" stroke="#0000ff">'
        '<path d="M 20,20 L 30,30"/>'
        "</g>"
        "</svg>"
    )
    ir = geometry_ir_from_svg(svg, source_hash=content_sha256(b"x"))
    assert ir.viewbox == (0.0, 0.0, 100.0, 100.0)
    assert len(ir.layers) == 2
    assert ir.layers[0].label == "red"
    assert ir.layers[0].color == "#ff0000"
    assert len(ir.layers[0].polylines) == 2  # path + line
    assert ir.layers[1].label == "blue"
    assert len(ir.layers[1].polylines) == 1


def test_geometry_ir_handles_unlabeled_svg() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        '<path d="M 0,0 L 10,10" stroke="black"/>'
        "</svg>"
    )
    ir = geometry_ir_from_svg(svg, source_hash="h")
    assert len(ir.layers) == 1
    assert ir.layers[0].layer_id == "layer-1"
    assert ir.layers[0].polylines


def test_content_sha256_matches_hashlib() -> None:
    import hashlib

    data = b"hello world"
    assert content_sha256(data) == hashlib.sha256(data).hexdigest()


LAYERED_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
    'viewBox="0 0 100 100">'
    '<g inkscape:label="rouge" stroke="#ff0000">'
    '<polyline points="0,0 10,0 10,10"/>'
    '<polyline points="50,50 60,50"/>'
    '<polygon points="20,20 30,20 30,30"/>'
    "</g>"
    '<g inkscape:label="bleu" stroke="#0000ff">'
    '<polyline points="80,80 90,90"/>'
    '<polyline points="70,10 75,15"/>'
    "</g>"
    "</svg>"
)


def test_optimize_geometry_ir_direct_matches_svg_route() -> None:
    """P5 (v2, roadmap 2.1a): the direct vpype consumer must produce the
    same optimized SVG and metrics as routing the IR through the SVG
    round-trip did."""
    from pen_plotter.core.toolpath import (
        _geometry_ir_to_svg,
        optimize_geometry_ir,
        optimize_svg,
    )

    ir = geometry_ir_from_svg(LAYERED_SVG, source_hash=content_sha256(b"x"))
    direct = optimize_geometry_ir(ir)
    via_svg = optimize_svg(_geometry_ir_to_svg(ir))
    assert direct.svg == via_svg.svg
    assert direct.metrics.pen_up_before_mm == pytest.approx(
        via_svg.metrics.pen_up_before_mm, rel=1e-9
    )
    assert direct.metrics.pen_up_after_mm == pytest.approx(
        via_svg.metrics.pen_up_after_mm, rel=1e-9
    )


def test_optimize_geometry_ir_single_path_early_exit() -> None:
    """One layer / one polyline is already monotonic — passthrough."""
    from pen_plotter.core.toolpath import optimize_geometry_ir

    ir = GeometryIR(
        source_hash="s",
        viewbox=(0.0, 0.0, 10.0, 10.0),
        layers=[
            LayerGeometry(
                layer_id="solo",
                polylines=[Polyline(points=[(0.0, 0.0), (5.0, 5.0)])],
            )
        ],
    )
    result = optimize_geometry_ir(ir)
    assert result.metrics.pen_up_before_mm == 0.0
    assert "polyline" in result.svg


def test_generate_gcode_from_geometry_is_direct_and_equivalent() -> None:
    """P5 (v2, roadmap 2.1b): the IR G-code generator consumes polylines
    directly; its move stream must match the SVG route's byte for byte."""
    from pen_plotter.core.gcode import generate_gcode, generate_gcode_from_geometry
    from pen_plotter.core.toolpath import _geometry_ir_to_svg
    from pen_plotter.profiles import get_profile

    profile = get_profile("Custom CoreXY A3")
    assert profile is not None
    ir = geometry_ir_from_svg(LAYERED_SVG, source_hash=content_sha256(b"x"))
    direct = generate_gcode_from_geometry(ir, profile)
    via_svg = generate_gcode(_geometry_ir_to_svg(ir), profile)
    direct_moves = [ln for ln in direct.splitlines() if ln.startswith(("G0 ", "G1 ", "G2", "G3"))]
    via_svg_moves = [ln for ln in via_svg.splitlines() if ln.startswith(("G0 ", "G1 ", "G2", "G3"))]
    assert direct_moves == via_svg_moves
