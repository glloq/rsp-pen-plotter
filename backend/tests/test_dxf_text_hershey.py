"""Hershey re-render for DXF TEXT / MTEXT entities.

Without the toggle, ezdxf's SVG backend renders each glyph as a filled
outline path — a pen plotter would double-trace the silhouette and the
result is illegible. With ``hershey_text=True``, the converter extracts
the model-space TEXT / MTEXT entries, strips the outline paths from the
SVG, and overlays single-stroke Hershey polylines at the same position.
"""

import io
import xml.etree.ElementTree as ET

import ezdxf

from pen_plotter.converters.dxf import DxfConverter

_INKSCAPE_LABEL = "{http://www.inkscape.org/namespaces/inkscape}label"


def _make_dxf(*, with_text: bool = True, with_mtext: bool = False, rotated: bool = False) -> bytes:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    # Geometry so the bounding box is well-defined.
    msp.add_line((0, 0), (100, 0))
    msp.add_line((0, 0), (0, 100))
    if with_text:
        t = msp.add_text("DXFtext", dxfattribs={"height": 8})
        t.set_placement((20, 50))
        if rotated:
            t.dxf.rotation = 45.0
    if with_mtext:
        m = msp.add_mtext("alpha\nbeta", dxfattribs={"char_height": 6})
        m.dxf.insert = (10, 80)
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def test_dxf_without_hershey_keeps_outline_text() -> None:
    """Default behaviour: ezdxf's filled-outline glyphs survive."""
    result = DxfConverter().convert(_make_dxf(), options={})
    # ezdxf emits the text as a series of filled <path> elements; the
    # conversion succeeds without raising.
    assert "<svg" in result.svg


def test_dxf_hershey_text_layer_present_when_enabled() -> None:
    """Enabling ``hershey_text`` adds a dedicated text layer."""
    result = DxfConverter().convert(_make_dxf(), options={"hershey_text": True, "font": "futural"})
    root = ET.fromstring(result.svg)
    labels = {child.get(_INKSCAPE_LABEL) for child in root.iter()}
    assert "text" in labels


def test_dxf_hershey_handles_mtext_multilines() -> None:
    """MTEXT with embedded newlines becomes one span per line."""
    result = DxfConverter().convert(
        _make_dxf(with_text=False, with_mtext=True),
        options={"hershey_text": True, "font": "futural"},
    )
    # Two lines of MTEXT → at least two pen-down M commands in the
    # Hershey text layer.
    root = ET.fromstring(result.svg)
    text_layer = next(child for child in root.iter() if child.get(_INKSCAPE_LABEL) == "text")
    serialised = ET.tostring(text_layer, encoding="unicode")
    assert serialised.count("M") >= 2


def test_dxf_hershey_warns_on_rotated_text() -> None:
    """Rotated TEXT is skipped with a warning rather than placed wrong."""
    result = DxfConverter().convert(
        _make_dxf(rotated=True),
        options={"hershey_text": True, "font": "futural"},
    )
    assert any("rotated" in w.lower() for w in result.warnings)


def test_dxf_hershey_text_lands_inside_the_mm_viewbox() -> None:
    """Regression: the Hershey overlay must be rebased into mm like the rest.

    ezdxf renders into a ~1 000 000-unit canvas; ``postprocess_dxf_svg``
    rebases the document into mm and stamps a ``scale(...)`` transform on
    every group. The spliced Hershey group is built in the raw million-unit
    space, so without the *same* transform its glyphs stay at ~1e6-unit
    coordinates and land thousands× off-page, blowing up the drawing bbox.
    """
    import re

    result = DxfConverter().convert(_make_dxf(), options={"hershey_text": True, "font": "futural"})
    root = ET.fromstring(result.svg)
    vb = (root.get("viewBox") or "").split()
    assert len(vb) == 4
    view_w, view_h = float(vb[2]), float(vb[3])

    text_layer = next(child for child in root.iter() if child.get(_INKSCAPE_LABEL) == "text")

    # Effective coordinate = raw path number × the group's scale transform.
    scale = 1.0
    tf = text_layer.get("transform")
    if tf:
        m = re.search(r"scale\(\s*([-\d.eE]+)", tf)
        assert m, f"unexpected transform form: {tf!r}"
        scale = float(m.group(1))

    coords = [
        abs(float(tok))
        for path in text_layer.iter("{http://www.w3.org/2000/svg}path")
        for tok in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", path.get("d") or "")
    ]
    assert coords, "text layer has no path coordinates"
    effective_max = max(coords) * scale
    # On-page (with a generous glyph-extent margin); pre-fix this was ~1e6.
    assert effective_max <= max(view_w, view_h) * 3, (
        f"Hershey text extends to {effective_max:.1f} user units, far outside "
        f"the {view_w}×{view_h} mm viewBox — overlay was not rebased into mm."
    )


def test_dxf_hershey_disabled_emits_no_extra_text_layer() -> None:
    """When the toggle is off, no Hershey overlay is appended."""
    result = DxfConverter().convert(_make_dxf(), options={"hershey_text": False})
    root = ET.fromstring(result.svg)
    labels = [child.get(_INKSCAPE_LABEL) for child in root.iter()]
    # No "text" label produced by the converter (the per-colour groups
    # use ``color-…`` labels).
    assert "text" not in labels
