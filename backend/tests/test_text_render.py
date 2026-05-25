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
from pen_plotter.domain.print_plan import PrintPlan, TypographyPlan


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
) -> PrintPlan:
    """Build a PrintPlan with just the fields the rerender path reads."""
    return PrintPlan(
        svg=svg,
        profile_name="dummy",
        typography=typography,
        library_file_id=library_file_id,
        source_mime=source_mime,
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
    _seed_library_file(
        monkeypatch, tmp_path, file_id="txt-1", data=body, suffix=".txt"
    )
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
    _seed_library_file(
        monkeypatch, tmp_path, file_id="txt-font", data=body, suffix=".txt"
    )
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
    _seed_library_file(
        monkeypatch, tmp_path, file_id="wrap-1", data=body, suffix=".txt"
    )
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
