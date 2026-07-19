"""Tests for the in-pipeline text rerender (post-L5 plumbing).

Covers the application-layer helper that re-renders text sources from
the library bytes when ``PrintPlan.typography`` + ``library_file_id``
+ ``source_mime`` are all set. The legacy upload-time render path
(when any of those is missing) keeps using ``plan.svg`` unchanged —
verified by the negative cases.

These tests run the converter chain end-to-end through ``convert_file``
so the assertions exercise the same code path the upload endpoint
exercises; the only difference is *when* the bytes are converted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pen_plotter.application.file_library import file_dir
from pen_plotter.application.text_render import (
    plan_with_rerendered_svg,
    rerender_text_svg,
    typography_to_options,
)
from pen_plotter.domain.print_plan import PlacementPlan, PrintPlan, TypographyPlan
from pen_plotter.models import MachineProfile, WorkspaceBounds


def _seed_library_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    file_id: str,
    data: bytes,
    suffix: str = ".txt",
) -> None:
    """Write ``data`` to ``<files_dir>/<file_id>/original<suffix>``."""
    monkeypatch.setenv("OMNIPLOT_FILES_DIR", str(tmp_path))
    target_dir = file_dir(file_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / f"original{suffix}").write_bytes(data)


def _text_plan(
    *,
    library_file_id: str | None,
    source_mime: str | None,
    typography: TypographyPlan | None,
    svg: str = "<svg/>",
    placement: PlacementPlan | None = None,
    scale_mode: str = "actual",
    margin_mm: float = 0.0,
) -> PrintPlan:
    """Build a PrintPlan with just the fields the rerender path reads."""
    return PrintPlan(
        svg=svg,
        profile_name="dummy",
        typography=typography,
        library_file_id=library_file_id,
        source_mime=source_mime,
        placement=placement,
        scale_mode=scale_mode,
        margin_mm=margin_mm,
    )


# ---- typography_to_options -------------------------------------------------


def test_typography_to_options_mirrors_typography_plan_fields() -> None:
    """The options dict carries every TypographyPlan field by the same name.

    The converters read the dict keyed by the field names listed here;
    any future TypographyPlan field MUST be added to both sides at
    once or the converter silently ignores it.
    """
    typo = TypographyPlan(
        font="rowmant",
        font_size_mm=18.0,
        page_width_mm=200.0,
        page_height_mm=300.0,
        margin_mm=12.5,
        line_spacing=2.0,
        alignment="center",
        stroke_width_mm=0.5,
        bold=True,
        italic=True,
        letter_spacing_mm=1.25,
    )
    options = typography_to_options(typo)
    assert options["font"] == "rowmant"
    assert options["font_size_mm"] == 18.0
    assert options["page_width_mm"] == 200.0
    assert options["page_height_mm"] == 300.0
    assert options["margin_mm"] == 12.5
    assert options["line_spacing"] == 2.0
    assert options["alignment"] == "center"
    assert options["stroke_width_mm"] == 0.5
    assert options["bold"] is True
    assert options["italic"] is True
    assert options["letter_spacing_mm"] == 1.25


def test_typography_to_options_defaults_hershey_text_on() -> None:
    """``hershey_text`` defaults to True so PDF / DOCX re-renders Hershey-replay.

    The text / markdown converters always Hershey-render and ignore
    this flag; the document converters use it to switch between the
    source's TrueType outlines and the single-stroke replay. When the
    operator opts into the typography path, they want the Hershey
    version — defaulting the flag on matches that expectation.
    """
    options = typography_to_options(TypographyPlan())
    assert options["hershey_text"] is True


# ---- rerender_text_svg negative cases (legacy path stays the fallback) -----


def test_rerender_text_svg_returns_none_without_typography() -> None:
    """No typography → no opt-in → no rerender."""
    plan = _text_plan(library_file_id="abc", source_mime="text/plain", typography=None)
    assert rerender_text_svg(plan) is None


def test_rerender_text_svg_returns_none_without_library_file_id() -> None:
    """No file id → we have no bytes to re-render from."""
    plan = _text_plan(
        library_file_id=None,
        source_mime="text/plain",
        typography=TypographyPlan(),
    )
    assert rerender_text_svg(plan) is None


def test_rerender_text_svg_returns_none_without_source_mime() -> None:
    """No mime → we can't pick a converter."""
    plan = _text_plan(
        library_file_id="abc",
        source_mime=None,
        typography=TypographyPlan(),
    )
    assert rerender_text_svg(plan) is None


def test_rerender_text_svg_returns_none_for_non_text_mime() -> None:
    """Image / SVG MIMEs don't have a typography render path.

    A vector / bitmap placement might accidentally carry a typography
    block from a sibling text placement during scene rehydrate; the
    rerender path short-circuits so the wrong converter never gets
    invoked.
    """
    plan = _text_plan(
        library_file_id="abc",
        source_mime="image/png",
        typography=TypographyPlan(),
    )
    assert rerender_text_svg(plan) is None


@pytest.mark.parametrize(
    "mime",
    [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.oasis.opendocument.text",
        "application/rtf",
        "text/html",
    ],
)
def test_rerender_text_svg_skips_document_sources(mime: str) -> None:
    """PDF / DOCX / HTML / RTF / ODT are not eligible for the in-pipeline rerender.

    Regression cover: when these MIMEs were on the eligible list, the
    /generate path replaced the frontend's composite SVG (workspace-mm
    coordinates) with the converter's raw output (document-intrinsic
    units, e.g. PDF points). Combined with ``scale_mode="actual"``,
    strokes ended up 2.83× too large and centred on the wrong region.
    Multi-page PDFs additionally lost the operator's page selection
    because ``TypographyPlan`` carries no ``page`` field.
    """
    plan = _text_plan(
        library_file_id="abc",
        source_mime=mime,
        typography=TypographyPlan(),
    )
    assert rerender_text_svg(plan) is None


def test_rerender_text_svg_returns_none_when_library_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """File id pointing at nothing on disk → graceful fallback to plan.svg.

    Operators can delete library files between the editor's last
    activity and a /generate call. The rerender path must NOT crash
    the job; the plan's pre-rendered SVG is the safety net.
    """
    monkeypatch.setenv("OMNIPLOT_FILES_DIR", str(tmp_path))
    plan = _text_plan(
        library_file_id="ghost",
        source_mime="text/plain",
        typography=TypographyPlan(),
    )
    assert rerender_text_svg(plan) is None


# ---- rerender_text_svg happy path (text / markdown / pdf MIMEs) ------------


def test_rerender_text_svg_renders_plain_text_from_library(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Plain-text source → converter runs against the library bytes.

    Asserts the rerender produces an SVG (the converter's output) and
    that the SVG markup looks like Hershey output: it should contain
    polyline / path elements, not a placeholder.
    """
    body = b"Hello\nWorld\n"
    _seed_library_file(monkeypatch, tmp_path, file_id="txt-1", data=body, suffix=".txt")
    plan = _text_plan(
        library_file_id="txt-1",
        source_mime="text/plain",
        typography=TypographyPlan(font="futural", font_size_mm=12.0),
    )
    svg = rerender_text_svg(plan)
    assert svg is not None
    assert svg.startswith("<")
    # Hershey output ships polylines (single-stroke text). A bug that
    # routed bytes to the wrong converter would emit a different shape.
    assert "polyline" in svg or "path" in svg


def test_rerender_text_svg_uses_typography_font(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Switching the TypographyPlan font produces a different SVG.

    Pin against the operator's complaint pre-L5b: changing the font
    in the editor used to require a re-upload. With this path the
    same library bytes should re-render under a different Hershey
    face and produce a measurably different SVG payload.
    """
    body = b"Hello World\n"
    _seed_library_file(monkeypatch, tmp_path, file_id="txt-font", data=body, suffix=".txt")
    plan_default = _text_plan(
        library_file_id="txt-font",
        source_mime="text/plain",
        typography=TypographyPlan(font="futural"),
    )
    plan_serif = _text_plan(
        library_file_id="txt-font",
        source_mime="text/plain",
        typography=TypographyPlan(font="rowmant"),
    )
    svg_default = rerender_text_svg(plan_default)
    svg_serif = rerender_text_svg(plan_serif)
    assert svg_default is not None
    assert svg_serif is not None
    assert svg_default != svg_serif


# ---- plan_with_rerendered_svg (the wrapper services call) ------------------


def test_plan_with_rerendered_svg_swaps_svg_on_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When the rerender succeeds, ``plan.svg`` is replaced."""
    body = b"Hello\n"
    _seed_library_file(monkeypatch, tmp_path, file_id="wrap-1", data=body, suffix=".txt")
    plan = _text_plan(
        library_file_id="wrap-1",
        source_mime="text/plain",
        typography=TypographyPlan(),
        svg="<svg>STALE</svg>",
    )
    out = plan_with_rerendered_svg(plan)
    assert out.svg != "<svg>STALE</svg>"
    # Other fields ride through unchanged so the application services
    # keep using ``out.layers`` / ``out.profile_name`` as before.
    assert out.profile_name == plan.profile_name
    assert out.library_file_id == plan.library_file_id


def _profile(x_max: float = 297.0, y_max: float = 210.0) -> MachineProfile:
    """Minimal MachineProfile for placement-bake tests."""
    return MachineProfile(
        name="Test A4",
        units="mm",
        workspace=WorkspaceBounds(x_min=0.0, y_min=0.0, x_max=x_max, y_max=y_max),
        origin="top_left",
        gcode_dialect="grbl",
        pen_up_command="M280 P0 S40",
        pen_down_command="M280 P0 S90",
        tool_change_method="manual_pause",
        tool_change_command="M0",
        drawing_speed_mm_s=30.0,
        travel_speed_mm_s=120.0,
        acceleration_mm_s2=500.0,
        pen_slot_count=1,
        supports_arcs=False,
        arc_tolerance_mm=0.1,
        ebb=None,
        pens=[],
    )


def test_plan_with_rerendered_svg_bakes_placement_transform(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Rerender with profile + placement → SVG carries the placement transform.

    The frontend's composite SVG bakes the placement transform onto
    every placement (independent x / y scales + translate to workspace
    mm), so a plain ``scale_mode='actual'`` render lands at the right
    spot. The rerender drops that transform; without re-applying it
    the rendered text either overflows the workspace at native page
    mm or letterboxes inside the placement rect at uniform fit-scale.
    Baking the transform onto the rerendered SVG restores the exact
    composite behaviour: the inked content lands at the placement
    rectangle's position in workspace mm, with independent x / y
    scales so a non-proportional resize stretches the text the same
    way the plan tab shows.
    """
    body = b"Hello\n"
    _seed_library_file(monkeypatch, tmp_path, file_id="placed-1", data=body, suffix=".txt")
    placement = PlacementPlan(
        sheet_width_mm=100.0,
        sheet_height_mm=80.0,
        offset_x_mm=20.0,
        offset_y_mm=15.0,
    )
    plan = _text_plan(
        library_file_id="placed-1",
        source_mime="text/plain",
        typography=TypographyPlan(),
        svg="<svg>STALE</svg>",
        placement=placement,
    )
    out = plan_with_rerendered_svg(plan, _profile())
    # The SVG was swapped (no longer the placeholder) and a transform
    # was applied so the rendered geometry lives in workspace mm.
    assert "STALE" not in out.svg
    assert "matrix(" in out.svg
    # The viewBox was rewritten to the workspace bounds so downstream
    # svgelements reads coordinates in workspace mm.
    assert 'viewBox="0.0 0.0 297.0 210.0"' in out.svg or 'viewBox="0 0 297' in out.svg
    # ``scale_mode`` / ``margin_mm`` are NOT mutated — the baked SVG
    # already lives at the placement rect, so the plan's existing
    # actual-mode flow yields identity in ``_make_transform``.
    assert out.scale_mode == plan.scale_mode
    assert out.margin_mm == plan.margin_mm


def test_plan_with_rerendered_svg_bake_matches_placement_rect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The baked geometry's bbox matches the placement rectangle exactly.

    The point of baking the transform is that the generator can pass
    the SVG through verbatim and land at the right size. Measure the
    rerendered SVG with svgelements after the bake and confirm its
    bbox in workspace mm matches the operator's placement rectangle —
    independent of the page-mm size the typography defaulted to.
    """
    from pen_plotter.core.layers import _measure as _measure_svg

    body = b"Hello world\nSecond line\n"
    _seed_library_file(monkeypatch, tmp_path, file_id="placed-2", data=body, suffix=".txt")
    placement = PlacementPlan(
        sheet_width_mm=60.0,
        sheet_height_mm=40.0,
        offset_x_mm=25.0,
        offset_y_mm=30.0,
    )
    plan = _text_plan(
        library_file_id="placed-2",
        source_mime="text/plain",
        typography=TypographyPlan(),
        svg="<svg>STALE</svg>",
        placement=placement,
    )
    out = plan_with_rerendered_svg(plan, _profile())
    _, bbox = _measure_svg(out.svg)
    # Each axis matches the placement rectangle to within tight
    # tolerance — the baked transform is the affine that maps the
    # inked content bbox onto the placement rect.
    assert bbox.x_min == pytest.approx(placement.offset_x_mm, abs=0.05)
    assert bbox.y_min == pytest.approx(placement.offset_y_mm, abs=0.05)
    assert bbox.x_max == pytest.approx(
        placement.offset_x_mm + placement.sheet_width_mm, abs=0.05
    )
    assert bbox.y_max == pytest.approx(
        placement.offset_y_mm + placement.sheet_height_mm, abs=0.05
    )


def test_plan_with_rerendered_svg_skips_bake_without_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No profile passed → SVG is swapped but no transform is applied.

    Older test fixtures (and legacy callers) that don't have a profile
    handy still get the SVG swap, just without the placement-bake. The
    G-code generator then falls back to centring the raw page-mm bbox
    on the placement region — slightly off-size but no crash.
    """
    body = b"Hello\n"
    _seed_library_file(monkeypatch, tmp_path, file_id="placed-3", data=body, suffix=".txt")
    plan = _text_plan(
        library_file_id="placed-3",
        source_mime="text/plain",
        typography=TypographyPlan(),
        svg="<svg>STALE</svg>",
        placement=PlacementPlan(
            sheet_width_mm=50.0, sheet_height_mm=50.0, offset_x_mm=0.0, offset_y_mm=0.0
        ),
    )
    out = plan_with_rerendered_svg(plan)
    assert "STALE" not in out.svg
    assert "matrix(" not in out.svg


def test_plan_with_rerendered_svg_returns_input_unchanged_on_fallback() -> None:
    """When the rerender is skipped, the input plan flows through verbatim.

    The application services rely on this so they can chain the
    helper into a single expression: ``svg = plan_with_rerendered_svg
    (plan).svg`` always yields a valid SVG.
    """
    plan = _text_plan(
        library_file_id=None,
        source_mime=None,
        typography=None,
        svg="<svg>ORIGINAL</svg>",
    )
    out = plan_with_rerendered_svg(plan)
    # Same instance: ``model_copy`` is only invoked when an SVG swap
    # is actually applied.
    assert out is plan
    assert out.svg == "<svg>ORIGINAL</svg>"


# ---- in-pipeline optimization of the rerendered SVG ------------------------


def _svg_pen_up(svg: str) -> float:
    """Total pen-up travel of an SVG's polylines in document order.

    Mirrors how ``core.gcode._read_layers`` walks the pivot: labeled
    fragments in order, then each layer's lines in order — the exact
    sequence the plotter will travel.
    """
    from pen_plotter.core.layers import labeled_group_fragments
    from pen_plotter.core.toolpath import _doc_from_svg

    total = 0.0
    prev_end: complex | None = None
    for _label, fragment in labeled_group_fragments(svg):
        doc = _doc_from_svg(fragment)
        for collection in doc.layers.values():
            for line in collection:
                if len(line) < 2:
                    continue
                if prev_end is not None:
                    total += abs(complex(line[0]) - prev_end)
                prev_end = complex(line[-1])
    return total


def test_plan_with_rerendered_svg_optimizes_toolpaths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The rerendered SVG ships in optimized order, not raw Hershey order.

    Regression cover for audit_optimisation_trace_2026-07-19 §F1: the
    /generate-time text rerender used to replace the frontend-optimized
    SVG with the converter's raw output, nearly doubling pen-up travel
    on a dense text page. The wrapper now runs the toolpath optimizer on
    the fresh render, so its travel must beat the raw converter output.
    """
    body = ("Le trace optimise ses trajets avant le G-code\n" * 8).encode("utf-8")
    _seed_library_file(monkeypatch, tmp_path, file_id="opt-1", data=body, suffix=".txt")
    plan = _text_plan(
        library_file_id="opt-1",
        source_mime="text/plain",
        typography=TypographyPlan(font_size_mm=8.0),
    )
    raw = rerender_text_svg(plan)
    assert raw is not None
    out = plan_with_rerendered_svg(plan)
    assert _svg_pen_up(out.svg) < _svg_pen_up(raw)


def test_plan_with_rerendered_svg_falls_back_when_optimize_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An optimizer crash must never block generation — raw render flows through."""
    from pen_plotter.application import text_render as tr

    body = b"Hello\n"
    _seed_library_file(monkeypatch, tmp_path, file_id="opt-2", data=body, suffix=".txt")

    def boom(svg: str, **kwargs: object) -> object:
        raise RuntimeError("vpype exploded")

    monkeypatch.setattr(tr, "optimize_svg", boom)
    plan = _text_plan(
        library_file_id="opt-2",
        source_mime="text/plain",
        typography=TypographyPlan(),
        svg="<svg>STALE</svg>",
    )
    out = plan_with_rerendered_svg(plan)
    # The rerender still replaced the stale SVG; only the optimization
    # step was skipped.
    assert "STALE" not in out.svg
