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

from pen_plotter.application.file_library import read_original_bytes
from pen_plotter.converters.base import UnsupportedFormatError
from pen_plotter.converters.pipeline import convert_file
from pen_plotter.domain.print_plan import PrintPlan, TypographyPlan

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


def plan_with_rerendered_svg(plan: PrintPlan) -> PrintPlan:
    """Return ``plan`` with a freshly-rendered SVG if the typography path applies.

    Convenience wrapper that the application services call right
    before handing the plan to the engines. When no rerender is
    available the input is returned unchanged (so callers don't have
    to branch on the return shape).
    """
    fresh_svg = rerender_text_svg(plan)
    if fresh_svg is None:
        return plan
    return plan.model_copy(update={"svg": fresh_svg})
