"""Tests for the PDF post-processing chain.

These cover the regression where PyMuPDF-derived SVG produced empty G-code
because (a) text glyphs lived behind ``<use>`` references that sanitize was
wiping out, and (b) embedded raster ``<image>`` elements were silently
ignored by vpype. The post-processing must inline ``<use>`` and vectorize
``<image>`` into a labeled sibling layer.
"""

from __future__ import annotations

import io
import re
from xml.etree import ElementTree as ET

import pymupdf
from PIL import Image

from pen_plotter.converters.pdf import PdfConverter
from pen_plotter.core.layers import extract_layers
from pen_plotter.core.pdf_postprocess import (
    expand_use_refs,
    extract_bitmap_options,
    hoist_labeled_groups,
    postprocess_pdf_svg,
    vectorize_embedded_images,
    wrap_text_layer,
)
from pen_plotter.core.sanitize import sanitize_svg
from pen_plotter.core.toolpath import optimize_svg

_SVG_NS = "http://www.w3.org/2000/svg"
_INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"


def _text_only_pdf() -> bytes:
    pdf = pymupdf.open()
    page = pdf.new_page(width=200, height=200)
    page.insert_text((10, 30), "Hello", fontsize=14)
    return pdf.write()


def _text_and_image_pdf() -> bytes:
    pdf = pymupdf.open()
    page = pdf.new_page(width=200, height=200)
    page.insert_text((10, 30), "Hello", fontsize=14)
    img = Image.new("RGB", (50, 50), (0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    page.insert_image(pymupdf.Rect(10, 50, 60, 100), stream=buf.getvalue())
    return pdf.write()


def test_expand_use_refs_inlines_local_targets() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<defs><path id="g1" d="M0 0L10 10"/></defs>'
        '<use xlink:href="#g1" transform="translate(5 5)"/>'
        "</svg>"
    )
    root = ET.fromstring(svg)
    expanded = expand_use_refs(root)
    out = ET.tostring(root, encoding="unicode")
    assert expanded == 1
    assert "<use" not in out
    # The expanded geometry now lives wrapped in a transform-bearing group.
    assert "translate(5 5)" in out
    assert 'd="M0 0L10 10"' in out


def test_expand_use_refs_drops_external_use() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<use xlink:href="https://example.com/evil.svg#a"/>'
        "</svg>"
    )
    root = ET.fromstring(svg)
    expand_use_refs(root)
    assert "<use" not in ET.tostring(root, encoding="unicode")


def test_vectorize_embedded_images_creates_labeled_group() -> None:
    # Build an SVG with a single black 4x4 PNG embedded as <image>.
    import base64

    img = Image.new("RGB", (8, 8), (0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        f'<image x="10" y="20" width="8" height="8" xlink:href="data:image/png;base64,{b64}"/>'
        "</svg>"
    )
    root = ET.fromstring(svg)
    produced, warnings = vectorize_embedded_images(root)
    assert produced == 1
    assert warnings == []
    out = ET.tostring(root, encoding="unicode")
    assert "<image" not in out
    assert 'inkscape:label="image-1"' in out


def test_vectorize_embedded_images_skips_external_href() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<image x="0" y="0" width="10" height="10" xlink:href="https://example.com/x.png"/>'
        "</svg>"
    )
    root = ET.fromstring(svg)
    produced, warnings = vectorize_embedded_images(root)
    assert produced == 0
    assert warnings  # at least one warning
    assert "<image" not in ET.tostring(root, encoding="unicode")


def test_hoist_labeled_groups_moves_nested_label_to_root() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">'
        '<g transform="translate(5 5)">'
        '<g inkscape:label="image-1" transform="scale(2)">'
        '<path d="M0 0L1 1"/>'
        "</g></g>"
        "</svg>"
    )
    root = ET.fromstring(svg)
    moved = hoist_labeled_groups(root)
    assert moved == 1
    # image-1 should now be a direct child of <svg>, with the parent transform
    # composed into its own transform attribute.
    direct_children = list(root)
    labeled = [c for c in direct_children if c.get(f"{{{_INKSCAPE_NS}}}label") == "image-1"]
    assert len(labeled) == 1
    assert "translate(5 5)" in (labeled[0].get("transform") or "")
    assert "scale(2)" in (labeled[0].get("transform") or "")


def test_wrap_text_layer_skips_already_labeled_children() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape">'
        '<g inkscape:label="image-1"><path d="M0 0L1 1"/></g>'
        '<path d="M2 2L3 3"/>'
        "</svg>"
    )
    root = ET.fromstring(svg)
    wrapped = wrap_text_layer(root)
    assert wrapped
    labels = [c.get(f"{{{_INKSCAPE_NS}}}label") for c in root]
    assert "text" in labels
    assert "image-1" in labels


def test_pdf_converter_preserves_text_through_sanitize() -> None:
    """Regression: text used to be removed by sanitize because PyMuPDF emits
    it via ``<use>`` references that were on the sanitizer's blocklist."""
    svg = PdfConverter().convert(_text_only_pdf()).svg
    clean = sanitize_svg(svg)
    layers = extract_layers(clean)
    assert layers, "post-processed PDF must produce at least one layer"
    text_layer = next((layer for layer in layers if layer.layer_id == "text"), None)
    assert text_layer is not None
    # Five glyphs in "Hello" → at least one stroke segment per glyph
    assert text_layer.path_count >= 5
    assert text_layer.total_length_mm > 0.0


def test_pdf_with_image_produces_two_layers() -> None:
    """Text and embedded raster must end up in separate labeled layers."""
    result = PdfConverter().convert(_text_and_image_pdf())
    clean = sanitize_svg(result.svg)
    layers = extract_layers(clean)
    labels = {layer.layer_id for layer in layers}
    assert "text" in labels
    assert "image-1" in labels
    # Each layer has its own non-empty geometry.
    for layer in layers:
        assert layer.path_count > 0, f"layer {layer.layer_id} is empty"
        assert layer.total_length_mm > 0.0


def test_pdf_with_image_produces_non_empty_gcode_geometry() -> None:
    """End-to-end: the optimized SVG retains drawable strokes for both layers."""
    result = PdfConverter().convert(_text_and_image_pdf())
    clean = sanitize_svg(result.svg)
    optimized = optimize_svg(clean)
    labels = re.findall(r'inkscape:label="([^"]+)"', optimized.svg)
    assert "text" in labels
    assert "image-1" in labels
    # vpype produced at least one <path> per labeled group.
    assert optimized.svg.count("<path") >= 2


def test_postprocess_handles_unparseable_svg_gracefully() -> None:
    out, warnings = postprocess_pdf_svg("<not-valid svg")
    assert out == "<not-valid svg"
    assert warnings


def test_sanitize_keeps_local_use_but_removes_external() -> None:
    """Defense-in-depth: even if a converter forgets to expand, sanitize keeps
    local ``<use>`` (the safe case) and drops external ones."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<defs><path id="a" d="M0 0L1 1"/></defs>'
        '<use xlink:href="#a"/>'
        '<use xlink:href="https://evil.example/x.svg#a"/>'
        "</svg>"
    )
    cleaned = sanitize_svg(svg)
    # The local <use> survives; the external one is removed.
    assert cleaned.count("<use") == 1
    assert "#a" in cleaned
    assert "evil.example" not in cleaned


def test_html_with_text_produces_text_layer() -> None:
    """Same regression as PDF, via the WeasyPrint → PyMuPDF route."""
    from pen_plotter.converters.html import HtmlConverter

    result = HtmlConverter().convert(b"<h1>Title</h1><p>Body text.</p>")
    clean = sanitize_svg(result.svg)
    layers = extract_layers(clean)
    text_layer = next((layer for layer in layers if layer.layer_id == "text"), None)
    assert text_layer is not None
    assert text_layer.path_count > 0
    assert text_layer.total_length_mm > 0.0


# Hershey re-render — when ``hershey_text=True``, the PDF converter
# strips PyMuPDF's original glyph outlines and plays the text back as
# single-stroke Hershey polylines at the same baseline positions. This
# is the only legible way to plot document text with a pen, since
# outline-traced TrueType glyphs paint as a double-traced silhouette.
def _bold_text_pdf() -> bytes:
    pdf = pymupdf.open()
    page = pdf.new_page(width=210, height=297)
    page.insert_text((50, 50), "Hello plotter", fontname="helv", fontsize=12)
    page.insert_text((50, 80), "Bold heading", fontname="hebo", fontsize=20)
    page.draw_rect((10, 10, 200, 100), color=(1, 0, 0))
    return pdf.write()


def test_pdf_hershey_strips_original_text_glyphs() -> None:
    res = PdfConverter().convert(_bold_text_pdf(), options={"hershey_text": True})
    # No PyMuPDF glyph traces left — neither the data-text marker nor
    # the font_X_NN definitions.
    assert "data-text" not in res.svg
    assert "font_1_" not in res.svg


def test_pdf_hershey_produces_drawings_and_text_layers() -> None:
    """Hershey owns the ``text`` label; the rest goes to ``drawings``."""
    res = PdfConverter().convert(_bold_text_pdf(), options={"hershey_text": True})
    clean = sanitize_svg(res.svg)
    labels = sorted(layer.layer_id for layer in extract_layers(clean))
    assert labels == ["drawings", "text"]


def test_pdf_hershey_text_layer_carries_continuous_strokes() -> None:
    """Each Hershey glyph stroke is one continuous polyline (not a
    series of disconnected M-L pairs the way the broken renderer
    produced before the strokes_for_text fix)."""
    res = PdfConverter().convert(
        _bold_text_pdf(), options={"hershey_text": True, "font": "futural"}
    )
    # The text layer's path d-string has more L commands than M commands
    # when strokes are continuous (M = pen down, L = line segment).
    match = re.search(r'inkscape:label="text"[^>]*>(.*?)</svg', res.svg, re.DOTALL)
    assert match is not None
    body = match.group(1)
    m_count = body.count("M")
    l_count = body.count(" L")
    assert m_count > 0
    assert l_count > m_count, f"strokes should be continuous (M={m_count}, L={l_count})"


def test_pdf_hershey_default_does_not_run() -> None:
    """No ``hershey_text`` option means no Hershey re-render — the
    original PyMuPDF glyph outlines stay intact for backward compat."""
    res = PdfConverter().convert(_bold_text_pdf())
    # data-text disappears after expand_use_refs, but the inlined glyph
    # paths remain — many M commands and a single "text" layer (no
    # separate "drawings" layer because Hershey wasn't injected).
    labels = sorted(layer.layer_id for layer in extract_layers(sanitize_svg(res.svg)))
    assert labels == ["text"]


def test_pdf_hershey_font_choice_changes_output() -> None:
    """Different Hershey faces produce visibly different geometry."""
    res_a = PdfConverter().convert(
        _bold_text_pdf(), options={"hershey_text": True, "font": "futural"}
    )
    res_b = PdfConverter().convert(
        _bold_text_pdf(), options={"hershey_text": True, "font": "timesr"}
    )
    assert res_a.svg != res_b.svg


# Cross-converter audit: the operator's font choice MUST reach both
# the SVG preview and the generated G-code, for every text-bearing
# source. Regression — earlier changes to the dedup path silently
# dropped typography keys on the .txt path; this test family makes
# sure each file type round-trips a font change end-to-end.
def _hershey_text_layer_strokes(svg: str) -> int:
    match = re.search(r'inkscape:label="text"[^>]*>(.*?)</svg', svg, re.DOTALL)
    body = match.group(1) if match else svg
    return body.count("M")


def test_txt_font_choice_changes_svg() -> None:
    from pen_plotter.converters.text import TextConverter

    conv = TextConverter()
    svg_a = conv.convert(b"Audit text", options={"font_size_mm": 10.0, "font": "futural"}).svg
    svg_b = conv.convert(b"Audit text", options={"font_size_mm": 10.0, "font": "timesr"}).svg
    assert svg_a != svg_b
    # Times Roman has noticeably more strokes per glyph than the
    # simplex sans-serif futural, so the M count is a quick sanity
    # check that the FONT actually changed (not just whitespace).
    assert svg_b.count("M") > svg_a.count("M")


def test_md_font_choice_changes_svg() -> None:
    from pen_plotter.converters.markdown import MarkdownConverter

    conv = MarkdownConverter()
    svg_a = conv.convert(b"# Audit text", options={"font_size_mm": 10.0, "font": "futural"}).svg
    svg_b = conv.convert(b"# Audit text", options={"font_size_mm": 10.0, "font": "timesib"}).svg
    assert svg_a != svg_b


def test_pdf_hershey_font_choice_changes_text_layer() -> None:
    """Already covered by ``test_pdf_hershey_font_choice_changes_output``
    but pinned here as part of the cross-converter audit so a future
    refactor of the audit set keeps PDF in scope."""
    res_a = PdfConverter().convert(
        _bold_text_pdf(), options={"hershey_text": True, "font": "futural"}
    )
    res_b = PdfConverter().convert(
        _bold_text_pdf(), options={"hershey_text": True, "font": "timesrb"}
    )
    a = _hershey_text_layer_strokes(res_a.svg)
    b = _hershey_text_layer_strokes(res_b.svg)
    assert a != b


def test_pdf_without_hershey_text_ignores_font_option() -> None:
    """Negative control: without ``hershey_text``, the font option is
    not applied (the original glyph outlines are preserved) and the
    SVG is byte-identical regardless of the requested Hershey face."""
    res_a = PdfConverter().convert(_bold_text_pdf(), options={"font": "futural"})
    res_b = PdfConverter().convert(_bold_text_pdf(), options={"font": "timesrb"})
    assert res_a.svg == res_b.svg


def test_extract_bitmap_options_forwards_every_rendering_field() -> None:
    """Guards against silently dropping a Style/Image-tab knob on the
    way to the embedded-raster pipeline. The five document-style
    converters (PDF/DOCX/HTML/EPS/SVG) share this helper so any field
    missing here would fail to apply to image regions of a mixed
    text+image source — the operator's custom palette, mono ink
    colour, segmentation method or photo preprocess would silently
    revert to defaults for those regions while text + vector content
    rendered with the operator's choices.
    """
    palette = ["#112233", "#445566"]
    preprocess = {"brightness": 1.2, "contrast": 0.9}
    algo_opts = {"spacing": 0.4, "angle_deg": 30}
    seg_opts = {"palette": palette}
    opts = {
        # Bitmap-rendering keys that MUST flow through.
        "algorithm": "hatching",
        "num_colors": 6,
        "max_dimension_px": 1600,
        "drop_background": False,
        "background_luminance": 0.8,
        "algorithm_options": algo_opts,
        "segmentation_method": "fixed_palette",
        "segmentation_options": seg_opts,
        "min_region_pixels": 12,
        "merge_delta_e": 2.5,
        "mono_ink_color": "#abcdef",
        "preprocess": preprocess,
        # Unrelated top-level keys that MUST be filtered out (they belong
        # to the surrounding document context, not the bitmap converter).
        "page": 3,
        "source_mime": "application/pdf",
        "hershey_text": True,
        "font": "futural",
        "stroke_width_mm": 0.4,
        # Frontend persistence extras the bitmap converter never reads.
        "master_style_id": "pencil",
        "curves": {"centerline_mode": False},
    }
    forwarded = extract_bitmap_options(opts)
    assert forwarded is not None
    assert forwarded == {
        "algorithm": "hatching",
        "num_colors": 6,
        "max_dimension_px": 1600,
        "drop_background": False,
        "background_luminance": 0.8,
        "algorithm_options": algo_opts,
        "segmentation_method": "fixed_palette",
        "segmentation_options": seg_opts,
        "min_region_pixels": 12,
        "merge_delta_e": 2.5,
        "mono_ink_color": "#abcdef",
        "preprocess": preprocess,
    }


def test_extract_bitmap_options_returns_none_for_empty_input() -> None:
    """An empty opts dict (or no opts) collapses to ``None`` so the
    downstream converter call keeps its default bitmap-converter
    behaviour instead of being handed an empty dict that would
    overwrite defaults with Pydantic's own zero-values."""
    assert extract_bitmap_options(None) is None
    assert extract_bitmap_options({}) is None
    # Only unrelated keys → still ``None``.
    assert extract_bitmap_options({"page": 1, "hershey_text": True}) is None
