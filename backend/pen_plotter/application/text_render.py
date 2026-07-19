"""In-pipeline text rerender for ``/preflight`` and ``/generate``.

Closes the gap left after L5: ``TypographyPlan`` rode the pivot for
traceability, but the actual text→SVG render still happened at upload
time. Changing the font / page / Hershey toggle in the editor required
``_reprocess_existing`` (a re-upload + re-conversion of the same
bytes). With this module the operator can edit the typography on a
text source and the next ``/preflight`` + ``/generate`` re-renders
straight from the library bytes — no re-upload step.

The helper is opt-in: when ``PrintPlan.library_file_id`` and
``PrintPlan.source_mime`` are both populated and there's a
``TypographyPlan`` attached, the application services swap the
plan's ``svg`` for the freshly converted one. Otherwise (older
clients, non-text placements, missing library file) ``plan.svg``
flows through unchanged — the legacy upload-time render remains the
fallback.

The plan_hash isn't affected: it's computed against the typography
settings + library_file_id + source_mime, not the resulting SVG.
Two preflight + generate calls with the same plan always agree.
"""

from __future__ import annotations

import logging
from typing import Any
from xml.etree import ElementTree as ET

from pen_plotter.application.file_library import read_original_bytes
from pen_plotter.converters.base import UnsupportedFormatError
from pen_plotter.converters.pipeline import convert_file
from pen_plotter.core.layers import _measure
from pen_plotter.core.svg_ns import svg_tostring
from pen_plotter.core.toolpath import LayerOptimization, optimize_svg
from pen_plotter.domain.print_plan import PlacementPlan, PrintPlan, TypographyPlan
from pen_plotter.models import MachineProfile

_log = logging.getLogger(__name__)

# MIME types eligible for the in-pipeline rerender. Restricted to the
# two sources whose converter output is *already* in workspace
# millimetres + self-contained (Hershey-rendered text positioned via
# ``TypographyOptions``), so a fresh rerender produced at /generate
# time slots cleanly into the slot the original composite occupied.
#
# PDF / DOCX / HTML / RTF / ODT are deliberately excluded:
#   1. their converter output is in document-intrinsic units (points
#      for PDF), so replacing the frontend's composite SVG — which
#      has workspace-mm coordinates baked in by ``buildComposite``'s
#      placement transform — produces strokes 2.83× too large and
#      centred on the wrong region (the L5 rerender path strips the
#      placement transform);
#   2. ``TypographyPlan`` carries no ``page`` field, so a multi-page
#      PDF would always rerender page 0 regardless of the page the
#      operator selected on the plan tab.
#
# The PDF/DOCX/HTML Hershey-rerender intent is still reachable via
# Apply in the editor (which re-uploads through ``store.upload`` and
# regenerates a properly-composited placement); only the silent /
# /generate-time rerender path is closed.
_TEXT_MIMES: frozenset[str] = frozenset(
    {
        "text/plain",
        "text/markdown",
    }
)


def typography_to_options(typography: TypographyPlan) -> dict[str, Any]:
    """Project a :class:`TypographyPlan` to the converter options dict.

    Mirrors the shape the text converters expect on
    ``converter.convert(data, options=...)``. The same field names are
    used end-to-end (frontend's TypographyDraft, the pivot's
    TypographyPlan, the converter's TypographyOptions) so this is a
    field-for-field carry rather than a translation table — keeping
    it as an explicit helper makes the in-pipeline rerender path
    legible at the call site and gives unit tests one place to pin
    the shape against.
    """
    return {
        "font": typography.font,
        "font_size_mm": typography.font_size_mm,
        "page_width_mm": typography.page_width_mm,
        "page_height_mm": typography.page_height_mm,
        "margin_mm": typography.margin_mm,
        "line_spacing": typography.line_spacing,
        "alignment": typography.alignment,
        "stroke_width_mm": typography.stroke_width_mm,
        "bold": typography.bold,
        "italic": typography.italic,
        "letter_spacing_mm": typography.letter_spacing_mm,
        # The Hershey re-render toggle for PDF / DOCX / HTML sources.
        # ``TypographyPlan`` doesn't carry it explicitly because the
        # text / markdown converters always Hershey-render, but the
        # document converters use this flag to switch between the
        # source's TrueType outlines and the single-stroke replay.
        # Defaulting to ``True`` makes the in-pipeline rerender behave
        # as the operator expects when they tweaked typography: they
        # want the Hershey version of the document.
        "hershey_text": True,
    }


def rerender_text_svg(plan: PrintPlan) -> str | None:
    """Re-render a text source's SVG from the library bytes if applicable.

    Returns the freshly-rendered SVG when **all** of these hold:

    * ``plan.typography`` is set (the operator opted into text
      rendering for this placement)
    * ``plan.library_file_id`` and ``plan.source_mime`` are populated
      (the client knows which bytes to feed back to the converter)
    * ``plan.source_mime`` is one of the text-source MIMEs we recognise
      (otherwise the rerender would be wasted CPU on a vector / image
      source whose typography setting is irrelevant)
    * the library file is still on disk (returns ``None`` if it
      vanished — the caller falls back to ``plan.svg``)
    * the converter accepts the typography options + produces an SVG
      (returns ``None`` on any conversion error so the legacy SVG
      stays the safety net)

    Returns ``None`` otherwise. The caller then uses ``plan.svg``
    as-is, preserving the legacy upload-time render path.
    """
    typography = plan.typography
    file_id = plan.library_file_id
    mime = plan.source_mime
    if typography is None or not file_id or not mime:
        return None
    if mime not in _TEXT_MIMES:
        return None

    data = read_original_bytes(file_id)
    if data is None:
        _log.info(
            "rerender_text_svg: library_file_id=%s not on disk; using plan.svg",
            file_id,
        )
        return None

    options = typography_to_options(typography)
    try:
        converted = convert_file(data, filename=None, mime=mime, options=options)
    except UnsupportedFormatError:
        # The MIME slipped through ``_TEXT_MIMES`` but the registry
        # disagrees — fall back to the plan SVG rather than fail the
        # whole job.
        _log.warning("rerender_text_svg: no converter for %s", mime)
        return None
    except Exception as exc:  # noqa: BLE001 — bare except is intentional
        # Any converter failure during in-pipeline render should NOT
        # block the generation pipeline. The legacy plan.svg is a safe
        # fallback (it was rendered at upload time with the previous
        # typography options).
        _log.warning("rerender_text_svg: converter raised %r; falling back", exc)
        return None
    return converted.svg


def _bake_placement_transform(
    svg: str, placement: PlacementPlan, profile: MachineProfile
) -> str:
    """Wrap the rerendered SVG's content in the placement transform.

    The frontend's composite SVG bakes a placement transform onto each
    placement that maps the source's intrinsic coordinates to workspace
    millimetres — scaling each axis *independently* (so a non-uniform
    resize on the plan stretches the content) and translating to the
    operator's chosen position. The rerender replaces that composite
    with a raw page-mm SVG and loses the transform completely; without
    a re-application the text either overflows the workspace (at
    ``scale='actual'``) or renders uniformly-scaled with a letterbox
    gap (at ``scale='fit'``) — neither matches what the plan tab shows.

    This helper re-applies the equivalent transform: it measures the
    rerendered SVG's inked bbox, computes the affine that maps that
    bbox onto the placement rectangle (in workspace mm) with
    independent x / y scales, and prepends it as a ``transform``
    attribute on every top-level labeled group. The viewBox is
    rewritten to the workspace bounds so downstream svgelements reads
    every stroke in workspace mm. The G-code generator then sees
    geometry that already lives at the right place and size: at
    ``scale_mode='actual'`` with the same placement attached, the
    transform inside ``_make_transform`` collapses to identity and the
    output matches the plan-tab preview exactly — including any
    non-proportional resize the operator applied.

    Returns the input unchanged if the SVG can't be parsed or has no
    measurable geometry (the caller falls back to the unbaked SVG).
    """
    _, bbox = _measure(svg)
    bw = bbox.x_max - bbox.x_min
    bh = bbox.y_max - bbox.y_min
    if bw <= 0 or bh <= 0:
        return svg

    ws = profile.workspace
    target_x = ws.x_min + placement.offset_x_mm
    target_y = ws.y_min + placement.offset_y_mm
    sx = placement.sheet_width_mm / bw
    sy = placement.sheet_height_mm / bh
    bbox_cx = (bbox.x_min + bbox.x_max) / 2.0
    bbox_cy = (bbox.y_min + bbox.y_max) / 2.0
    target_cx = target_x + placement.sheet_width_mm / 2.0
    target_cy = target_y + placement.sheet_height_mm / 2.0
    tx = target_cx - sx * bbox_cx
    ty = target_cy - sy * bbox_cy
    matrix = f"matrix({sx:.6f} 0 0 {sy:.6f} {tx:.6f} {ty:.6f})"

    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg

    ws_w = ws.x_max - ws.x_min
    ws_h = ws.y_max - ws.y_min
    root.set("viewBox", f"{ws.x_min} {ws.y_min} {ws_w} {ws_h}")
    if "width" in root.attrib:
        root.set("width", f"{ws_w}mm")
    if "height" in root.attrib:
        root.set("height", f"{ws_h}mm")

    # Apply the matrix to each direct child element — typically the
    # single labeled group emitted by ``HersheyRenderer``. Prepending
    # to any existing transform preserves SVG's right-to-left
    # composition order (placement wraps around child transforms).
    # The labeled groups have to stay top-level for
    # ``labeled_group_fragments`` to find them — wrapping in an extra
    # ``<g>`` would hide them from the layer extractor and collapse
    # every layer into a single ``layer-1`` fallback.
    touched = False
    for child in list(root):
        tag = child.tag.rsplit("}", 1)[-1]
        if tag in {"defs", "metadata", "title", "desc"}:
            continue
        existing = child.get("transform")
        child.set("transform", f"{matrix} {existing}" if existing else matrix)
        touched = True
    if not touched:
        return svg

    return svg_tostring(root)


def plan_with_rerendered_svg(
    plan: PrintPlan, profile: MachineProfile | None = None
) -> PrintPlan:
    """Return ``plan`` with a freshly-rendered SVG if the typography path applies.

    Convenience wrapper that the application services call right
    before handing the plan to the engines. When no rerender is
    available the input is returned unchanged (so callers don't have
    to branch on the return shape).

    When the rerender swaps the SVG **and** the plan carries a
    placement **and** a profile was supplied, the helper also bakes the
    placement transform into the new SVG so the generated geometry
    lands exactly where the plan tab shows it — same position, same
    size, same independent-axis stretch the operator applied with a
    non-proportional resize. Callers that don't pass a profile (older
    test fixtures) get the legacy behaviour: the SVG is swapped but
    no transform is applied, leaving the generator to centre the raw
    page-mm bbox on the placement region.

    The rerendered SVG then goes through the toolpath optimizer
    (``core.toolpath.optimize_svg``): the fresh converter output would
    otherwise ship to the engines in raw Hershey emission order,
    silently discarding the optimization the frontend applied to the
    placement it replaces — measured at nearly double the pen-up
    travel on a dense text page (audit_optimisation_trace_2026-07-19
    §F1). Runs after the placement bake so the optimizer sees the
    final geometry; falls back to the unoptimized render on any
    failure, because the rerender path must never block generation.
    """
    fresh_svg = rerender_text_svg(plan)
    if fresh_svg is None:
        return plan
    if plan.placement is not None and profile is not None:
        fresh_svg = _bake_placement_transform(fresh_svg, plan.placement, profile)
    fresh_svg = _optimize_rerendered_svg(fresh_svg, plan)
    return plan.model_copy(update={"svg": fresh_svg})


def _optimize_rerendered_svg(svg: str, plan: PrintPlan) -> str:
    """Run the toolpath optimizer on a rerendered SVG, best-effort.

    The plan's per-layer ``optimize`` / ``simplify_tolerance_mm`` settings
    are forwarded so an operator's opt-out is honoured when the layer
    labels of the fresh render match the plan's layer ids (labels that
    don't match simply fall back to the optimizer defaults).
    """
    settings = [
        LayerOptimization(
            layer_id=layer.layer_id,
            optimize=layer.optimize,
            simplify_tolerance_mm=layer.simplify_tolerance_mm or 0.05,
        )
        for layer in plan.layers
    ]
    try:
        return optimize_svg(svg, layers=settings).svg
    except Exception as exc:  # noqa: BLE001 — same safety net as rerender_text_svg
        _log.warning("optimize of rerendered text svg failed (%r); using raw render", exc)
        return svg
