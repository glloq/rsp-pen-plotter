"""DXF converter.

Renders DXF modelspace entities to SVG using the ezdxf drawing add-on with
its native SVG backend, then runs :func:`postprocess_dxf_svg` to strip the
editor-background ``<rect>`` (which would otherwise plot as a giant frame)
and re-bucket drawables by colour class into ``<g inkscape:label="color-…">``
groups so multi-colour DXF drawings keep their per-colour separation as
distinct plotter layers.

When the operator enables Hershey text re-render, TEXT and MTEXT entities
are extracted from the model BEFORE rendering, ezdxf's text outline output
is stripped from the resulting SVG, and the text is redrawn as single-stroke
Hershey polylines at the same modelspace position. This is the only way to
actually plot DXF text — ezdxf's SVG backend emits each glyph as filled
outlines, which a pen plotter would double-trace into an illegible
silhouette.
"""

from __future__ import annotations

import io
import re
from typing import Any, ClassVar
from xml.etree import ElementTree as ET

import ezdxf
from ezdxf import bbox
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.layout import Page
from ezdxf.addons.drawing.svg import SVGBackend

from pen_plotter.converters.base import ConversionResult, Converter
from pen_plotter.core.dxf_postprocess import postprocess_dxf_svg
from pen_plotter.typography import PlacedSpan, render_placed_spans


def _extract_dxf_text_entities(msp: Any) -> list[tuple[str, float, float, float, float]]:
    """Pull TEXT / MTEXT entities out of the modelspace.

    Returns a list of ``(text, x, y, height, rotation_deg)`` tuples in
    DXF modelspace coordinates (Y up). MTEXT bodies are split on newlines
    so each visual line becomes its own span — the Hershey layout flow
    has no concept of a multi-line text entity.
    """
    entries: list[tuple[str, float, float, float, float]] = []
    for entity in msp:
        kind = entity.dxftype()
        if kind == "TEXT":
            text = entity.dxf.text or ""
            if not text.strip():
                continue
            insert = entity.dxf.insert
            entries.append(
                (
                    text,
                    float(insert[0]),
                    float(insert[1]),
                    float(entity.dxf.height),
                    float(getattr(entity.dxf, "rotation", 0.0) or 0.0),
                )
            )
        elif kind == "MTEXT":
            text = entity.text or ""
            if not text.strip():
                continue
            insert = entity.dxf.insert
            height = float(entity.dxf.char_height)
            rotation = float(getattr(entity.dxf, "rotation", 0.0) or 0.0)
            # MTEXT y is the top of the first line; subsequent lines step
            # down by 1.5 × char_height (DXF's default line spacing).
            x0, y0 = float(insert[0]), float(insert[1])
            for i, line in enumerate(text.split("\n")):
                if not line.strip():
                    continue
                entries.append(
                    (line, x0, y0 - i * height * 1.5, height, rotation)
                )
    return entries


def _parse_svg_transform(svg: str) -> tuple[float, float, float, float, float] | None:
    """Recover the model→SVG transform from the ezdxf SVG output.

    ezdxf's SVG backend emits ``width="W mm" height="H mm" viewBox="0 0 vw vh"``.
    Combined with the modelspace extents we can derive a uniform scale and
    a y-flip. Returns ``(scale, vh, extmin_x, extmin_y, extmax_y)`` or
    ``None`` if the SVG is unparseable.
    """
    m_vb = re.search(r'viewBox="\s*0\s+0\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*"', svg)
    if not m_vb:
        return None
    vw, vh = float(m_vb.group(1)), float(m_vb.group(2))
    if vw <= 0 or vh <= 0:
        return None
    return vw, vh, 0.0, 0.0, 0.0  # caller fills extents


def _build_dxf_hershey_group(
    doc: Any, msp: Any, raw_svg: str, opts: dict[str, Any]
) -> str:
    """Build a Hershey ``<g>`` overlay for the DXF's TEXT / MTEXT entities.

    Coordinates are mapped from modelspace (Y up) into the ezdxf SVG's
    viewBox (Y down) using the SVG's viewBox dimensions and the DXF's
    modelspace extents. Returns the empty string when ``hershey_text`` is
    disabled or no text entities are present.
    """
    if not bool(opts.get("hershey_text", False)):
        return ""
    entries = _extract_dxf_text_entities(msp)
    if not entries:
        return ""

    parsed = _parse_svg_transform(raw_svg)
    if parsed is None:
        return ""
    vw, vh, _, _, _ = parsed
    try:
        extents = bbox.extents(msp)
    except Exception:
        return ""
    extmin_x = float(extents.extmin.x)
    extmin_y = float(extents.extmin.y)
    extmax_x = float(extents.extmax.x)
    extmax_y = float(extents.extmax.y)
    ext_w = extmax_x - extmin_x
    ext_h = extmax_y - extmin_y
    if ext_w <= 0 or ext_h <= 0:
        return ""
    # ezdxf preserves aspect ratio when fitting model → page; the smaller
    # of the two axis scales wins so the drawing isn't distorted.
    scale = min(vw / ext_w, vh / ext_h)
    if scale <= 0:
        return ""

    spans: list[PlacedSpan] = []
    for text, mx, my, height, rotation in entries:
        # DXF rotation is around the insertion point. Hershey rendering
        # doesn't apply rotation — entities with a non-zero rotation get
        # placed at the insertion point but drawn horizontally. Rotated
        # labels are a known limitation; common engineering DXFs use
        # horizontal text. (Rotation could be added later by wrapping each
        # span in its own <g transform="rotate(...)">.)
        if abs(rotation) > 0.5:
            continue
        sx = (mx - extmin_x) * scale
        # Y flip: model y grows up, SVG y grows down. DXF TEXT insertion
        # is at the baseline already (matches Hershey's expectation).
        sy = vh - (my - extmin_y) * scale
        spans.append(
            PlacedSpan(
                text=text,
                x=sx,
                baseline_y=sy,
                size=height * scale,
            )
        )

    if not spans:
        return ""
    # The Hershey path is in viewBox units (svg_unit ≠ mm here); use a
    # stroke width that scales with the drawing's scale so it stays
    # visible. The simulator overrides stroke width at render time anyway.
    stroke_width = max(scale * float(opts.get("stroke_width_mm", 0.3)), 1.0)
    return render_placed_spans(spans, font=str(opts.get("font", "futural")),
                               stroke_width=stroke_width)


def _strip_text_outlines_from_dxf_svg(svg: str) -> str:
    """Remove the filled glyph outlines ezdxf emits for TEXT/MTEXT.

    ezdxf renders text as ``<g>`` blocks of ``<path class="C2">`` (the
    fill-only class — see ``dxf_postprocess._class_colors``) containing
    closed sub-paths that trace each glyph silhouette. Stripping every
    fill-class group is too aggressive (it would remove SOLID hatches),
    so we look for the specific pattern: a ``<g>`` whose only children
    are ``class="C2"`` paths AND whose immediate previous sibling chain
    contains no stroked drawables for the same logical entity.

    Pragmatic implementation: remove every ``<path class="Cn">`` whose
    class definition has ``stroke: none; fill: …`` — that's ezdxf's
    text/SOLID class. SOLID hatch is rarer than text in plotter input
    and the operator can disable Hershey if they need filled hatches.
    """
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg

    # Discover which classes are fill-only (ezdxf text glyphs).
    fill_only: set[str] = set()
    for elem in root.iter():
        if elem.tag.endswith("}style") or elem.tag == "style":
            body = elem.text or ""
            for cls, decl in re.findall(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", body):
                if re.search(r"stroke\s*:\s*none", decl) and re.search(r"fill\s*:\s*#", decl):
                    fill_only.add(cls)
    if not fill_only:
        return svg

    parent_map = {child: parent for parent in root.iter() for child in parent}
    removed_paths = 0
    for elem in list(root.iter()):
        if not elem.tag.endswith("}path") and elem.tag != "path":
            continue
        cls = elem.get("class") or ""
        if cls in fill_only:
            parent = parent_map.get(elem)
            if parent is not None:
                parent.remove(elem)
                removed_paths += 1
    if removed_paths == 0:
        return svg
    return ET.tostring(root, encoding="unicode")


class DxfConverter(Converter):
    """Converts a DXF drawing's modelspace to the SVG pivot format."""

    supported_mimes: ClassVar[frozenset[str]] = frozenset(
        {"image/vnd.dxf", "application/dxf", "image/x-dxf"}
    )

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Convert DXF bytes to SVG.

        Args:
            data: Raw DXF file bytes (UTF-8 or latin-1 text).
            options: Optional ``hershey_text``/``font``/``stroke_width_mm``
                to replace TEXT/MTEXT entities with single-stroke
                polylines. Other options accepted for interface
                compatibility.

        Returns:
            A :class:`ConversionResult` containing the post-processed SVG —
            background rect removed, drawables grouped per colour class,
            and (when enabled) TEXT/MTEXT redrawn with the chosen Hershey
            font.

        Raises:
            ValueError: If the bytes are not a parseable DXF document.
        """
        opts = options or {}
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        try:
            doc = ezdxf.read(io.StringIO(text))
        except ezdxf.DXFError as exc:
            raise ValueError(f"Invalid DXF document: {exc}") from exc

        msp = doc.modelspace()
        backend = SVGBackend()
        Frontend(RenderContext(doc), backend).draw_layout(msp)
        raw_svg = backend.get_string(Page(0, 0))

        hershey_enabled = bool(opts.get("hershey_text", False))
        hershey_group = _build_dxf_hershey_group(doc, msp, raw_svg, opts)
        if hershey_enabled:
            # Strip the outline glyphs whenever the toggle is on, even if
            # the overlay turned out empty (e.g. every TEXT was rotated)
            # — otherwise the original double-traced silhouettes survive
            # and the operator's "I asked for Hershey" intent is lost.
            raw_svg = _strip_text_outlines_from_dxf_svg(raw_svg)

        svg = postprocess_dxf_svg(raw_svg)

        if hershey_group:
            # Splice the Hershey overlay before the closing </svg> tag so
            # extract_layers picks it up as a top-level labeled group.
            close = svg.rfind("</svg>")
            if close != -1:
                svg = svg[:close] + hershey_group + svg[close:]

        warnings: list[str] = []
        if hershey_enabled:
            # Rotated entities are skipped; warn once if any TEXT/MTEXT in
            # the file has a non-zero rotation so the operator knows.
            for entity in msp:
                kind = entity.dxftype()
                if kind not in {"TEXT", "MTEXT"}:
                    continue
                rotation = float(getattr(entity.dxf, "rotation", 0.0) or 0.0)
                if abs(rotation) > 0.5:
                    warnings.append(
                        "Some DXF TEXT/MTEXT entities are rotated; rotated text is "
                        "not yet supported by the Hershey re-render and was skipped."
                    )
                    break

        return ConversionResult(svg=svg, source_mime="image/svg+xml", warnings=warnings)
