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


def test_html_colored_divs_split_into_one_layer_per_color() -> None:
    """A print-test page with red / green / blue / yellow boxes plus
    black text must produce one labeled layer per color, not collapse
    every shape into a single ``text`` group with the first encountered
    fill as its representative swatch.
    """
    from pen_plotter.converters.html import HtmlConverter

    html = b"""<!doctype html><html><head><style>
      .box { display:inline-block; width:30mm; height:20mm; }
      .red { background:#ff0000; } .green { background:#00aa00; }
      .blue { background:#0066ff; } .yellow { background:#ffd400; }
    </style></head><body>
      <h1>Title</h1>
      <div class="box red"></div><div class="box green"></div>
      <div class="box blue"></div><div class="box yellow"></div>
    </body></html>"""
    result = HtmlConverter().convert(html)
    clean = sanitize_svg(result.svg)
    layers = extract_layers(clean)
    labels = {layer.layer_id for layer in layers}
    # One label per box color, plus the black "text" group for the heading.
    assert "color-#ff0000" in labels
    assert "color-#00aa00" in labels
    assert "color-#0066ff" in labels
    assert "color-#ffd400" in labels
    assert "text" in labels
    # Each color layer must carry the matching swatch so the frontend
    # doesn't show a default-black chip for a red layer.
    by_label = {layer.layer_id: layer for layer in layers}
    assert by_label["color-#ff0000"].source_color == "#ff0000"
    assert by_label["color-#00aa00"].source_color == "#00aa00"
    # Every color layer carries non-empty geometry.
    for label in ("color-#ff0000", "color-#00aa00", "color-#0066ff", "color-#ffd400"):
        assert by_label[label].path_count > 0


def test_html_grayscale_swatches_fold_into_one_density_modulated_layer() -> None:
    """A printer-test grayscale ramp (several greys at different lightness)
    must produce a SINGLE black ``grayscale`` layer with hatching density
    proportional to each swatch's darkness — not one ``color-#nnnnnn``
    layer per shade. The whole ramp routes to one black pen out of the
    box, and the operator doesn't have to dedupe a dozen near-identical
    layers.
    """
    from pen_plotter.converters.html import HtmlConverter

    html = b"""<!doctype html><html><head><style>
      .bar { display:inline-block; width:20mm; height:15mm; }
    </style></head><body>
      <div class="bar" style="background:#1a1a1a"></div>
      <div class="bar" style="background:#4d4d4d"></div>
      <div class="bar" style="background:#808080"></div>
      <div class="bar" style="background:#b3b3b3"></div>
      <div class="bar" style="background:#e6e6e6"></div>
    </body></html>"""
    result = HtmlConverter().convert(html, options={"algorithm": "crosshatch"})
    layers = {layer.layer_id: layer for layer in extract_layers(sanitize_svg(result.svg))}

    # All grays collapse into one black layer.
    assert "grayscale" in layers, f"expected a 'grayscale' layer; got {sorted(layers)}"
    assert layers["grayscale"].source_color == "#000000"
    # And no per-shade ``color-#nnnnnn`` layers survive on this page —
    # otherwise the operator would be back to manually merging swatches.
    leaked = [
        label
        for label in layers
        if label.startswith("color-#")
        and label[7:] not in {"ffffff", "000000"}
        # ``label[7:]`` is the hex without the leading "color-#". Greys
        # have R==G==B; non-greys (cyan, etc.) wouldn't be leaked even
        # if grouping by colour kept them separate.
        and label[7:9] == label[9:11] == label[11:13]
    ]
    assert not leaked, f"grayscale swatches leaked into per-shade layers: {leaked}"
    # Hatching must actually cover the swatches — empty grayscale layer
    # would mean the helper found candidates but emitted nothing.
    assert layers["grayscale"].path_count > 20
    assert layers["grayscale"].total_length_mm > 100


def test_html_solid_color_fills_get_algorithm_rendering() -> None:
    """A colored CSS ``background-color`` div must plot the same way a
    PNG of the same area would: with the operator's chosen algorithm
    (crosshatch / halftone / stippling / …) actually filling the
    rectangle, not leaving a flat outline that runs the pen along the
    border once and leaves the inside blank.

    The vector path defaulted to one ``M…Z`` outline per rectangle in
    the pre-fix pipeline. Asking for ``crosshatch`` must produce
    enough strokes per swatch that the count alone proves the algo
    actually ran on the rasterised crop.
    """
    from pen_plotter.converters.html import HtmlConverter

    html = b"""<!doctype html><html><head><style>
      .box { display:inline-block; width:30mm; height:20mm; }
    </style></head><body>
      <div class="box" style="background:#ff0000"></div>
      <div class="box" style="background:#0000ff"></div>
    </body></html>"""
    outline_result = HtmlConverter().convert(html, options={"algorithm": "direct"})
    outline_layers = {
        layer.layer_id: layer for layer in extract_layers(sanitize_svg(outline_result.svg))
    }
    hatched_result = HtmlConverter().convert(html, options={"algorithm": "crosshatch"})
    hatched_layers = {
        layer.layer_id: layer for layer in extract_layers(sanitize_svg(hatched_result.svg))
    }

    for color in ("color-#ff0000", "color-#0000ff"):
        assert color in outline_layers, f"missing color layer {color} in direct output"
        assert color in hatched_layers, f"missing color layer {color} in crosshatch output"
        # Crosshatch must put many parallel strokes inside each
        # rectangle; the direct outline is essentially one stroke per
        # corner. A 10× ratio is the safety floor that proves the
        # crosshatch algorithm actually ran on the rasterised crop
        # rather than the rectangle being left as a vector outline.
        assert hatched_layers[color].path_count > 10 * outline_layers[color].path_count, (
            f"{color}: crosshatch did not produce significantly more strokes than direct "
            f"(direct={outline_layers[color].path_count}, "
            f"crosshatch={hatched_layers[color].path_count})"
        )


def test_html_grayscale_gradient_rasterised_into_pattern_layer() -> None:
    """A CSS linear-gradient div arrives at PyMuPDF as an empty
    ``<pattern>`` reference; the post-processor must rasterise the
    corresponding page crop and run it through the bitmap converter
    so the gradient actually plots as halftoned strokes instead of
    leaving an invisible silhouette.
    """
    from pen_plotter.converters.html import HtmlConverter

    html = b"""<!doctype html><html><head><style>
      .grad { width:120mm; height:15mm;
              background: linear-gradient(to right, #000, #fff); }
    </style></head><body>
      <div class="grad"></div>
    </body></html>"""
    result = HtmlConverter().convert(html)
    clean = sanitize_svg(result.svg)
    layers = extract_layers(clean)
    pattern_layers = [layer for layer in layers if layer.layer_id.startswith("pattern-")]
    assert pattern_layers, (
        "expected at least one ``pattern-N`` layer for the gradient; "
        f"got {[layer.layer_id for layer in layers]}"
    )
    # The bitmap pipeline must actually have produced strokes — an
    # empty pattern layer would mean the rasterisation silently
    # dropped the gradient.
    assert pattern_layers[0].path_count > 0
    assert pattern_layers[0].total_length_mm > 0.0


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
    original PyMuPDF glyph outlines stay intact for backward compat.

    The fixture also contains a red rectangle drawn with
    ``page.draw_rect(..., color=(1, 0, 0))``; the fill-split path now
    surfaces that as its own ``color-#ff0000`` layer so the operator
    can route it to a red pen instead of having it ride along with
    the body text.
    """
    res = PdfConverter().convert(_bold_text_pdf())
    labels = sorted(layer.layer_id for layer in extract_layers(sanitize_svg(res.svg)))
    assert labels == ["color-#ff0000", "text"]


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


# -- Regressions for HTML-source artefacts ------------------------------


def _html_to_svg(html_str: str) -> str:
    """Run the full HTML → post-processed SVG pipeline for assertions."""
    from pen_plotter.converters.html import HtmlConverter

    converter = HtmlConverter()
    result = converter.convert(html_str.encode("utf-8"), options={})
    return sanitize_svg(result.svg)


def _layer_d_total(svg: str, label: str) -> int:
    """Return the summed length of every ``d=`` attribute in one labeled layer."""
    root = ET.fromstring(svg)
    for child in root:
        if child.tag != f"{{{_SVG_NS}}}g":
            continue
        if child.get(f"{{{_INKSCAPE_NS}}}label") != label:
            continue
        return sum(len(p.get("d", "")) for p in child.iter() if p.tag == f"{{{_SVG_NS}}}path")
    return 0


def test_html_text_glyphs_keep_their_ancestor_transform() -> None:
    """``split_loose_drawables_by_fill`` used to detach PyMuPDF glyph paths
    from the ``<g transform="matrix(font_size 0 0 -font_size x y)">``
    wrapper that ``expand_use_refs`` placed around them. Every glyph
    then collapsed to a 1-point dot at the origin and the text
    disappeared from both the editor preview and the gcode. The
    composed ancestor transform must survive the move."""
    svg = _html_to_svg(
        "<html><body><h1 style='font-family: sans-serif'>HELLO</h1></body></html>"
    )
    root = ET.fromstring(svg)
    text_group = next(
        (
            child
            for child in root
            if child.get(f"{{{_INKSCAPE_NS}}}label") == "text"
        ),
        None,
    )
    assert text_group is not None, "missing text layer"
    # Every glyph path that lives in 0..1 glyph-em coords must sit
    # inside a transform wrapper that scales it up.
    glyph_paths = [
        p for p in text_group.iter() if p.tag == f"{{{_SVG_NS}}}path" and p.get("d")
    ]
    assert glyph_paths, "expected glyph paths inside the text layer"
    parent_map = {child: parent for parent in text_group.iter() for child in parent}
    for path in glyph_paths:
        ancestor = parent_map.get(path)
        # Walk to text_group looking for any transform; text in 0..1
        # space is meaningless without it.
        found = False
        while ancestor is not None and ancestor is not text_group:
            if ancestor.get("transform"):
                found = True
                break
            ancestor = parent_map.get(ancestor)
        assert found, f"glyph path {path.get('d')[:40]!r} has no transform ancestor"


def test_html_colored_boxes_become_per_color_density_hatching() -> None:
    """A CSS ``background-color`` div used to plot as a bare potrace
    outline (3-4 paths per box) because ``rasterize_solid_color_fills``
    fell back to the default ``direct`` algorithm. With no operator
    bitmap options, the post-processor now applies per-colour density
    hatching so the box prints as a hatched rectangle."""
    svg = _html_to_svg(
        "<html><body>"
        "<div style='background:#ff0000;width:200px;height:60px'></div>"
        "<div style='background:#0000ff;width:200px;height:60px'></div>"
        "</body></html>"
    )
    layers = {layer.layer_id: layer for layer in extract_layers(svg)}
    assert "color-#ff0000" in layers
    assert "color-#0000ff" in layers
    # Hatching produces many short parallel paths; a bare outline yields
    # 3-4. Anything above ~10 means the fill rendered as hatching.
    assert layers["color-#ff0000"].path_count > 10
    assert layers["color-#0000ff"].path_count > 10
    # The hatched group's geometry length must dwarf an outline's
    # (~few hundred chars vs several thousand).
    assert _layer_d_total(svg, "color-#ff0000") > 1500


def test_html_text_renders_on_top_of_hatched_backgrounds() -> None:
    """A CSS ``background-color`` div with text inside used to plot the
    colour-hatching ON TOP of the text glyphs (because the hatching
    groups were appended at the end of the SVG and SVG draws later
    siblings above earlier ones). The operator read the result as
    "text struck through by hatch lines". The post-processor must put
    background-style labelled layers (``color-#xxxxxx`` and
    ``grayscale``) BEFORE the ``text`` layer in document order so text
    glyphs paint last and stay legible."""
    svg = _html_to_svg(
        "<html><body>"
        "<div style='background:#ffff00;width:200px;height:80px'></div>"
        "<div style='background:#cccccc;width:200px;height:80px'></div>"
        "<p>Plain text after coloured swatches.</p>"
        "</body></html>"
    )
    root = ET.fromstring(svg)
    labels: list[str] = []
    for child in root:
        if child.tag != f"{{{_SVG_NS}}}g":
            continue
        label = child.get(f"{{{_INKSCAPE_NS}}}label")
        if label:
            labels.append(label)
    assert "text" in labels, f"missing text layer in {labels}"
    text_idx = labels.index("text")
    # Every background-style layer (gray or color-hex) must come BEFORE
    # the text layer in document order, otherwise the hatching is drawn
    # on top of the glyphs.
    for i, label in enumerate(labels):
        if label == "grayscale" or label.startswith("color-"):
            assert i < text_idx, (
                f"background layer {label!r} (index {i}) is drawn AFTER "
                f"text (index {text_idx}); text would be struck through. "
                f"Full order: {labels}"
            )


def test_html_thin_gray_border_around_text_does_not_hatch_through() -> None:
    """A CSS ``border: 1px solid #ccc`` around a text line is emitted by
    WeasyPrint as a single ``<path>`` with two nested rectangle
    subpaths and ``fill-rule="evenodd"`` — the painted area is just
    the thin ring, but the path's AABB covers the entire interior
    including any text inside it. The grayscale density hatcher used
    to bbox-hatch the whole interior so the small text glyph rendered
    on top appeared "barred" by hatch lines. Frame-shaped paths
    (evenodd fill rule or multiple subpaths) must be left alone."""
    svg = _html_to_svg(
        "<html><body>"
        "<div style='border:1px solid #cccccc;padding:1mm;font-size:10px'>"
        "The quick brown fox</div>"
        "</body></html>"
    )
    root = ET.fromstring(svg)
    grayscale_group = next(
        (
            child
            for child in root
            if child.get(f"{{{_INKSCAPE_NS}}}label") == "grayscale"
        ),
        None,
    )
    # Either no grayscale layer was produced at all, or it carries
    # zero hatch lines — the only #ccc shape on the page is the
    # text-line border, and that must stay as an outline.
    if grayscale_group is not None:
        hatch_paths = [
            p
            for p in grayscale_group.iter()
            if p.tag == f"{{{_SVG_NS}}}path" and p.get("d")
        ]
        assert hatch_paths == [], (
            f"grayscale layer hatched {len(hatch_paths)} lines across a "
            "border-only path — text inside the border would be barred"
        )


def test_html_colored_box_with_text_inside_skips_hatching() -> None:
    """Any solid-coloured shape whose bbox contains text glyphs must NOT
    be density-hatched — bbox-hatching paints parallel lines across
    the glyphs and the operator reads the result as "text barred".
    A bordered-but-empty coloured div is still hatched (the original
    fix) so the regression doesn't flip the other way. Compares the
    two side by side: orange box with a heading inside vs a bare red
    box → the orange box drops to outline only, the red box stays
    fully hatched."""
    svg = _html_to_svg(
        "<html><body>"
        "<div style='background:#ffaa00;padding:20px;width:400px'>"
        "<p style='font-size:24px'>Heading on orange</p>"
        "</div>"
        "<div style='background:#ff0000;width:300px;height:80px'></div>"
        "</body></html>"
    )
    layers = {layer.layer_id: layer for layer in extract_layers(svg)}
    # Orange box wraps text → no hatching, just the outline.
    assert "color-#ffaa00" in layers
    assert layers["color-#ffaa00"].path_count <= 3, (
        "orange box with text inside should plot as outline only; "
        f"got {layers['color-#ffaa00'].path_count} paths "
        "(hatching is bleeding through the text)"
    )
    # Bare red box has no text → hatching still applies.
    assert "color-#ff0000" in layers
    assert layers["color-#ff0000"].path_count > 10, (
        "empty red box should still be hatched; "
        f"got only {layers['color-#ff0000'].path_count} paths"
    )


def test_html_explicit_black_swatch_plots_as_solid_hatching() -> None:
    """The dark end of the operator's grayscale ramp uses
    ``background-color: rgb(0, 0, 0)``. WeasyPrint emits black as the
    SVG default (no ``fill`` attribute) which the post-processor
    can't tell apart from the dozens of auxiliary no-fill paths
    WeasyPrint also emits, so the cell used to plot as a bare
    outline. ``HtmlConverter`` now rewrites every explicit pure-black
    background to ``#010101`` before WeasyPrint runs, which gives the
    swatch an unambiguous ``fill="#010101"`` for the grayscale
    density hatcher to pick up at min spacing."""
    svg = _html_to_svg(
        "<html><body>"
        "<div style='background:rgb(0,0,0);width:200px;height:80px'></div>"
        "<div style='background:#000;width:200px;height:80px'></div>"
        "<div style='background-color:black;width:200px;height:80px'></div>"
        "</body></html>"
    )
    layers = {layer.layer_id: layer for layer in extract_layers(svg)}
    assert "grayscale" in layers, (
        "explicit-black swatches must land in the grayscale layer once "
        "HtmlConverter has rewritten them to #010101"
    )
    # Three full-page-width black blocks @ ~200×80 produce a lot of
    # hatch line geometry — well into the hundreds of paths.
    assert layers["grayscale"].path_count > 60, (
        f"grayscale layer has only {layers['grayscale'].path_count} paths; "
        "the black swatches are plotting as outlines, not solid hatching"
    )


def test_path_bbox_handles_leading_dot_decimals() -> None:
    """``_path_bbox_user_units`` parses every numeric token in a path
    d-string. PyMuPDF emits glyph coords without a leading zero
    (``.61035158``), so a regex that requires a digit before the
    decimal point silently splits ``.61035158`` into ``61035158`` —
    producing astronomical bboxes and bogging the hatcher down in
    millions of phantom hatch lines (the print-test page never
    finished converting). The fixed regex accepts both forms."""
    from xml.etree import ElementTree as ET

    from pen_plotter.core.pdf_postprocess import _path_bbox_user_units

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">'
        '<path d="M.5151367 .15429688C.5151367 .1031901 .49422203 .063069667 .45239259 .033935548Z"/>'
        "</svg>"
    )
    root = ET.fromstring(svg)
    path = root[0]
    parent_map = {path: root}
    bbox = _path_bbox_user_units(path, parent_map, root)
    assert bbox is not None
    x_min, y_min, x_max, y_max = bbox
    # Every coord in the d-string is between 0 and 1, so the bbox must
    # stay in unit space — astronomical values mean the leading-dot
    # numbers were silently expanded into 9-digit integers.
    assert 0 <= x_min < 1 and 0 < x_max <= 1
    assert 0 <= y_min < 1 and 0 < y_max <= 1
