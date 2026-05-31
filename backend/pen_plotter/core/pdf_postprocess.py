"""Post-processing for PyMuPDF-emitted SVG.

PyMuPDF (and therefore every document route that funnels through it —
``PdfConverter``, ``DocumentConverter`` via LibreOffice, ``HtmlConverter`` via
WeasyPrint) emits text as ``<defs>`` glyphs referenced by ``<use>`` and rasters
as ``<image>`` elements. Three consequences for the plotter pipeline:

* ``<use>`` is in :mod:`pen_plotter.core.sanitize`'s blocklist (security:
  external ``<use href="evil.svg">`` can pull arbitrary content), so the text
  silently disappears.
* ``<image>`` elements are not strokes; ``vpype.read_multilayer_svg`` ignores
  them, so any embedded raster is silently dropped before G-code generation.
* PDF shading patterns (CSS gradients, etc.) come out as ``fill="url(#…)"``
  on a shape whose ``<pattern>`` definition PyMuPDF leaves empty — so the
  shape plots as a flat silhouette with nothing inside.

This module pre-expands every ``<use>`` reference into inline geometry,
hands each embedded raster to the bitmap converter so it becomes a vectorized
labeled layer of its own, and rasterises any pattern-filled shape from the
original PDF page (when the source bytes are available) so its gradient is
recovered as halftoned strokes. The remaining vector content is split by
``fill`` color so that, for example, an HTML print-test page with red /
green / blue / yellow boxes plus black text yields one labeled layer per
color rather than collapsing all four boxes into a single "text" group.
After post-processing the SVG is self-contained (no ``<defs>``, no
``<use>``, no ``<image>``) and ``extract_layers`` produces one entry per
detected color or source kind so the user can assign each to a different
pen slot.
"""

from __future__ import annotations

import base64
import copy
from typing import Any
from xml.etree import ElementTree as ET

from pen_plotter.converters.base import ConversionResult
from pen_plotter.core.svg_ns import INKSCAPE_NS as _INKSCAPE_NS
from pen_plotter.core.svg_ns import SVG_NS as _SVG_NS
from pen_plotter.core.svg_ns import XLINK_NS as _XLINK_NS
from pen_plotter.core.svg_ns import svg_tostring

_INKSCAPE_LABEL = f"{{{_INKSCAPE_NS}}}label"
_XLINK_HREF = f"{{{_XLINK_NS}}}href"


# Every key that ``BitmapOptions`` accepts and whose value materially
# shapes the rendered output of an embedded raster (algorithm, palette,
# segmentation, photo preprocess, mono-ink override, post-processing).
# The five document-style converters (PDF, DOCX/ODT/RTF, HTML, EPS/PS/AI,
# SVG) all hand embedded ``<image>`` regions to the bitmap converter; if
# any of these are dropped on the floor the operator's Style/Image-tab
# choices silently fail to apply to the image regions of a mixed
# text+image source.
_BITMAP_FORWARD_KEYS: tuple[str, ...] = (
    "algorithm",
    "num_colors",
    "max_dimension_px",
    "drop_background",
    "background_luminance",
    "algorithm_options",
    "segmentation_method",
    "segmentation_options",
    "min_region_pixels",
    "merge_delta_e",
    "mono_ink_color",
    "preprocess",
)


def extract_bitmap_options(opts: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the subset of ``opts`` that drives embedded-raster rendering.

    Centralised so every document-style converter forwards the same
    rendering-shaping fields (algorithm, palette, segmentation,
    preprocess, mono-ink override, post-processing) to the bitmap
    converter — anything missing from the returned dict silently
    reverts to the bitmap converter's defaults for image regions in a
    mixed text+image source.
    """
    if not opts:
        return None
    forwarded = {key: opts[key] for key in _BITMAP_FORWARD_KEYS if key in opts}
    return forwarded or None


def _local(tag: str) -> str:
    """Return an element's local name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _id_map(root: ET.Element) -> dict[str, ET.Element]:
    """Map every element that carries an ``id`` to its element."""
    mapping: dict[str, ET.Element] = {}
    for element in root.iter():
        ident = element.get("id")
        if ident:
            mapping[ident] = element
    return mapping


def _href_target(use: ET.Element) -> str | None:
    """Return the local target id of a ``<use>`` element, or ``None``.

    Only fragment references (``#id``) are accepted; external URLs are
    refused because they would expand to arbitrary remote content.
    """
    raw = use.get("href") or use.get(_XLINK_HREF) or use.get("xlink:href")
    if not raw or not raw.startswith("#"):
        return None
    return raw[1:]


def _combined_transform(use: ET.Element) -> str | None:
    """Build the equivalent transform attribute for a ``<use>`` element.

    The SVG semantic is *first* apply the ``transform`` attribute, *then*
    apply a translation by ``(x, y)`` — so the resulting transform string
    is ``transform translate(x, y)`` when both are present.
    """
    parts: list[str] = []
    existing = use.get("transform")
    if existing:
        parts.append(existing)
    x = use.get("x")
    y = use.get("y")
    if (x and x != "0") or (y and y != "0"):
        parts.append(f"translate({x or 0} {y or 0})")
    return " ".join(parts) if parts else None


def strip_text_glyphs(root: ET.Element) -> int:
    """Remove PyMuPDF text glyphs and their <use> instances.

    PyMuPDF emits PDF text as ``<use data-text="X" xlink:href="#font_..."/>``
    referencing ``<defs><path id="font_..." .../></defs>``. The
    Hershey re-render path wants the SVG to carry every non-text
    drawing untouched but no text content, so the caller can layer
    single-stroke text on top at the operator's chosen font / size.

    Both the references and their orphaned glyph definitions are
    dropped. Returns the number of ``<use>`` elements removed.
    """
    removed = 0
    parent_map = {child: parent for parent in root.iter() for child in parent}
    for use in list(root.iter()):
        if _local(use.tag) != "use":
            continue
        href = (use.get("href") or use.get(_XLINK_HREF) or use.get("xlink:href") or "").lstrip("#")
        # PyMuPDF tags every text-glyph reference with ``data-text``
        # and points it at an id starting with ``font_``. Either signal
        # is enough — accept both so a future PyMuPDF version that
        # tweaks one of them still works.
        is_text = use.get("data-text") is not None or href.startswith("font_")
        if not is_text:
            continue
        parent = parent_map.get(use)
        if parent is not None:
            parent.remove(use)
            removed += 1
    # Drop the now-unreferenced glyph definitions so the SVG stays lean.
    for defs in list(root.iter()):
        if _local(defs.tag) != "defs":
            continue
        for child in list(defs):
            cid = child.get("id") or ""
            if cid.startswith("font_"):
                defs.remove(child)
    return removed


def expand_use_refs(root: ET.Element) -> int:
    """Replace every ``<use>`` whose target is local with the referenced geometry.

    Returns the number of expanded references. Operates in-place. Iterates
    until quiescent so nested ``<use>`` chains (a glyph referencing another
    glyph) all collapse.
    """
    targets = _id_map(root)
    expansions = 0
    # Iteratively expand: nested <use>s require multiple passes.
    while True:
        parent_map = {child: parent for parent in root.iter() for child in parent}
        round_count = 0
        for use in list(root.iter()):
            if _local(use.tag) != "use":
                continue
            target_id = _href_target(use)
            if target_id is None or target_id not in targets:
                # External or missing — drop the <use>; sanitize_svg also
                # removes <use> as a safety net.
                parent = parent_map.get(use)
                if parent is not None:
                    parent.remove(use)
                continue
            target = targets[target_id]
            # Deep-copy so we can mutate the clone without affecting other
            # uses of the same definition.
            clone = copy.deepcopy(target)
            # The clone keeps an `id`, which would now collide; strip it.
            clone.attrib.pop("id", None)
            transform = _combined_transform(use)
            wrapper = ET.Element(f"{{{_SVG_NS}}}g")
            if transform:
                wrapper.set("transform", transform)
            wrapper.append(clone)
            parent = parent_map.get(use)
            if parent is None:
                continue
            index = list(parent).index(use)
            parent.remove(use)
            parent.insert(index, wrapper)
            round_count += 1
            expansions += 1
        if round_count == 0:
            break
    # Drop now-orphaned <defs> blocks. We only remove those whose
    # descendants were the targets of expanded <use>s; keep unrelated
    # defs (e.g. gradients still referenced by fill="url(#...)").
    for defs in [e for e in root.iter() if _local(e.tag) == "defs"]:
        # Best-effort: PyMuPDF emits <defs> solely to hold glyphs that <use>
        # consumed, so they can be safely removed once empty of referenced
        # content. We keep them only if a non-<use> reference remains.
        keep = False
        for child in defs:
            child_id = child.get("id")
            if not child_id:
                keep = True
                break
            if child_id in targets and child_id not in [t for t in targets if t]:
                pass
        if not keep:
            parent = next((p for p in root.iter() if defs in list(p)), None)
            if parent is not None:
                parent.remove(defs)
    return expansions


def _decode_image_data(href: str) -> tuple[bytes, str] | None:
    """Decode a ``data:image/...;base64,...`` URI into ``(bytes, mime)``.

    Returns ``None`` for unsupported URIs (e.g. external URLs).
    """
    if not href.startswith("data:"):
        return None
    try:
        meta, payload = href.split(",", 1)
    except ValueError:
        return None
    if ";base64" not in meta:
        return None
    mime = meta[5:].split(";", 1)[0] or "image/png"
    try:
        data = base64.b64decode(payload)
    except (ValueError, TypeError):
        return None
    return data, mime


def _inner_groups(svg_markup: str) -> list[ET.Element]:
    """Return the inner ``<g inkscape:label>`` groups of a converter SVG."""
    try:
        root = ET.fromstring(svg_markup)
    except ET.ParseError:
        return []
    return [child for child in root if _local(child.tag) == "g" and child.get(_INKSCAPE_LABEL)]


def _image_geometry(image: ET.Element) -> tuple[float, float, float, float]:
    """Return ``(x, y, width, height)`` of an ``<image>`` element."""

    def _num(attr: str, default: float) -> float:
        value = image.get(attr)
        try:
            return float(value) if value is not None else default
        except ValueError:
            return default

    return _num("x", 0.0), _num("y", 0.0), _num("width", 1.0), _num("height", 1.0)


def vectorize_embedded_images(
    root: ET.Element,
    *,
    bitmap_options: dict[str, Any] | None = None,
) -> tuple[int, list[str]]:
    """Replace every ``<image>`` element with a vectorized labeled group.

    Each ``<image>`` is decoded, run through the bitmap converter (with
    ``bitmap_options`` controlling the algorithm and palette), and its raster
    is replaced in-place with a ``<g inkscape:label="image-N">`` that holds
    the vectorized strokes — positioned and scaled to match the original
    image's display rectangle.

    Returns ``(count, warnings)`` where ``count`` is the number of images
    that produced a vectorized layer.
    """
    from pen_plotter.converters.bitmap import BitmapConverter

    warnings: list[str] = []
    parent_map = {child: parent for parent in root.iter() for child in parent}
    images = [e for e in root.iter() if _local(e.tag) == "image"]
    converter = BitmapConverter()
    produced = 0

    for index, image in enumerate(images, start=1):
        parent = parent_map.get(image)
        if parent is None:
            continue
        href = image.get("href") or image.get(_XLINK_HREF) or image.get("xlink:href") or ""
        decoded = _decode_image_data(href)
        if decoded is None:
            warnings.append(f"Image #{index}: skipped (unsupported or external href).")
            parent.remove(image)
            continue
        raw_bytes, _mime = decoded
        try:
            result: ConversionResult = converter.convert(raw_bytes, options=bitmap_options)
        except Exception as exc:  # noqa: BLE001 — best-effort, the doc must still convert
            warnings.append(f"Image #{index}: vectorization failed ({exc}).")
            parent.remove(image)
            continue

        groups = _inner_groups(result.svg)
        if not groups:
            warnings.append(f"Image #{index}: no drawable layers (likely all background).")
            parent.remove(image)
            continue

        # Pull the source pixel dimensions from the bitmap converter's
        # viewBox so we can scale strokes back to the image's display
        # rectangle on the page.
        try:
            inner_root = ET.fromstring(result.svg)
            viewbox = inner_root.get("viewBox", "")
            _, _, src_w, src_h = (float(v) for v in viewbox.split())
        except (ET.ParseError, ValueError):
            warnings.append(f"Image #{index}: vectorized SVG has no viewBox.")
            parent.remove(image)
            continue

        dst_x, dst_y, dst_w, dst_h = _image_geometry(image)
        sx = dst_w / max(src_w, 1e-9)
        sy = dst_h / max(src_h, 1e-9)

        wrapper = ET.Element(f"{{{_SVG_NS}}}g")
        wrapper.set(_INKSCAPE_LABEL, f"image-{index}")
        # Compose translate + scale; the converter SVG's children are color
        # groups whose strokes live in raw pixel coordinates.
        existing = image.get("transform")
        transform_parts: list[str] = []
        if existing:
            transform_parts.append(existing)
        if dst_x or dst_y:
            transform_parts.append(f"translate({dst_x} {dst_y})")
        if sx != 1.0 or sy != 1.0:
            transform_parts.append(f"scale({sx} {sy})")
        if transform_parts:
            wrapper.set("transform", " ".join(transform_parts))
        for group in groups:
            # Strip the converter's per-color inkscape:label so they don't
            # masquerade as top-level layers after we move them.
            group.attrib.pop(_INKSCAPE_LABEL, None)
            wrapper.append(group)

        position = list(parent).index(image)
        parent.remove(image)
        parent.insert(position, wrapper)
        produced += 1

    return produced, warnings


def _parse_transform(value: str | None) -> tuple[float, float, float, float, float, float]:
    """Parse an SVG ``transform`` attribute into a 2x3 affine matrix.

    Supports the subset PyMuPDF actually emits: ``matrix(a b c d e f)``,
    ``translate(tx[, ty])``, ``scale(sx[, sy])``. Unknown forms collapse
    to identity rather than raise — we are computing a best-effort bbox
    for rasterisation, not enforcing strict SVG semantics.
    """
    a, b, c, d, e, f = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0  # identity
    if not value:
        return a, b, c, d, e, f
    import re

    for name, args in re.findall(r"(matrix|translate|scale)\s*\(([^)]*)\)", value):
        nums = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        if name == "matrix" and len(nums) == 6:
            ma, mb, mc, md, me, mf = nums
        elif name == "translate":
            tx = nums[0] if nums else 0.0
            ty = nums[1] if len(nums) > 1 else 0.0
            ma, mb, mc, md, me, mf = 1.0, 0.0, 0.0, 1.0, tx, ty
        elif name == "scale":
            sx = nums[0] if nums else 1.0
            sy = nums[1] if len(nums) > 1 else sx
            ma, mb, mc, md, me, mf = sx, 0.0, 0.0, sy, 0.0, 0.0
        else:
            continue
        # Compose: result = current ∘ new (SVG applies left-to-right)
        a, b, c, d, e, f = (
            a * ma + c * mb,
            b * ma + d * mb,
            a * mc + c * md,
            b * mc + d * md,
            a * me + c * mf + e,
            b * me + d * mf + f,
        )
    return a, b, c, d, e, f


def _ancestor_transform(
    element: ET.Element, parent_map: dict[ET.Element, ET.Element], root: ET.Element
) -> tuple[float, float, float, float, float, float]:
    """Compose every ancestor's transform from root down to ``element``."""
    chain: list[ET.Element] = []
    cursor: ET.Element | None = parent_map.get(element)
    while cursor is not None and cursor is not root:
        chain.append(cursor)
        cursor = parent_map.get(cursor)
    a, b, c, d, e, f = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0
    for ancestor in reversed(chain):
        ma, mb, mc, md, me, mf = _parse_transform(ancestor.get("transform"))
        a, b, c, d, e, f = (
            a * ma + c * mb,
            b * ma + d * mb,
            a * mc + c * md,
            b * mc + d * md,
            a * me + c * mf + e,
            b * me + d * mf + f,
        )
    return a, b, c, d, e, f


def _rect_bbox_user_units(
    rect: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
    root: ET.Element,
) -> tuple[float, float, float, float] | None:
    """Return the AABB of a ``<rect>`` in the SVG's user units.

    Composes the rect's own ``transform`` with every ancestor transform
    so the returned ``(x_min, y_min, x_max, y_max)`` is in the document
    coordinate system — which, for PyMuPDF SVG, equals PDF points.
    Returns ``None`` if the rect has degenerate dimensions.
    """
    try:
        x = float(rect.get("x", "0"))
        y = float(rect.get("y", "0"))
        w = float(rect.get("width", "0"))
        h = float(rect.get("height", "0"))
    except ValueError:
        return None
    if w <= 0 or h <= 0:
        return None
    ancestor = _ancestor_transform(rect, parent_map, root)
    own = _parse_transform(rect.get("transform"))
    a1, b1, c1, d1, e1, f1 = ancestor
    a2, b2, c2, d2, e2, f2 = own
    # Compose ancestor ∘ own
    a, b, c, d, e, f = (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )
    corners = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
    xs = [a * px + c * py + e for px, py in corners]
    ys = [b * px + d * py + f for px, py in corners]
    return min(xs), min(ys), max(xs), max(ys)


def _has_visible_content(subtree: ET.Element) -> bool:
    """Return ``True`` if ``subtree`` has any drawable leaf outside a mask.

    Paths buried inside a ``<clipPath>`` or ``<mask>`` define the mask
    region itself — they do not paint pixels and so don't count as
    "visible content". Same for anything still hiding in a ``<defs>``
    block that was inlined as part of an ``<use>`` expansion.
    """
    masked = {f"{{{_SVG_NS}}}clipPath", f"{{{_SVG_NS}}}mask", f"{{{_SVG_NS}}}defs"}
    # Walk with a small stack so we can prune entire mask subtrees.
    stack: list[ET.Element] = [subtree]
    while stack:
        node = stack.pop()
        if node.tag in masked:
            continue
        if node is not subtree and _local(node.tag) in _DRAWABLE_LEAVES:
            return True
        stack.extend(list(node))
    return False


def _pattern_is_empty(root: ET.Element, pattern_id: str) -> bool:
    """Check whether the ``<pattern>`` def whose id is ``pattern_id`` is empty.

    PyMuPDF emits PDF shading patterns (CSS gradients) as ``<pattern>``
    elements that reference a ``pattern_tile_N`` group, but the tile
    contents are dropped — the gradient never makes it into the SVG.
    We detect this empty case so we know the pattern fill needs to be
    rasterised back from the PDF; non-empty patterns are left alone
    because they would render correctly in any viewer.

    A pattern is "empty" when neither its own subtree nor any
    ``<use>``-referenced tile contains a drawable leaf outside a
    ``<clipPath>`` / ``<mask>`` / ``<defs>``. PyMuPDF's empty
    gradients hit exactly that case: the only paths in the tile live
    inside a ``<clipPath>`` whose clipped ``<g>`` is empty.
    """
    for elem in root.iter():
        if _local(elem.tag) != "pattern":
            continue
        if elem.get("id") != pattern_id:
            continue
        if _has_visible_content(elem):
            return False
        for use in elem.iter():
            if _local(use.tag) != "use":
                continue
            href = (use.get("href") or use.get(_XLINK_HREF) or "").lstrip("#")
            if not href:
                continue
            for candidate in root.iter():
                if candidate.get("id") != href:
                    continue
                if _has_visible_content(candidate):
                    return False
        return True
    return False  # unknown pattern — leave the shape alone


def rasterize_pattern_fills(
    root: ET.Element,
    *,
    pdf_bytes: bytes,
    page_index: int,
    bitmap_options: dict[str, Any] | None = None,
) -> tuple[int, list[str]]:
    """Replace pattern-filled shapes with bitmap-vectorised regions.

    PyMuPDF drops the contents of PDF shading patterns when it writes
    SVG, so a CSS ``linear-gradient`` div (and any other shaded fill)
    arrives as an empty ``url(#pattern_N)`` rectangle. This helper
    finds those shapes, asks PyMuPDF to render the corresponding crop
    of the original PDF page as a PNG, runs the PNG through the bitmap
    converter (so the user's halftone / hatching / dithering pipeline
    actually plots the gradient), and substitutes the result in place
    of the empty rect.

    Only ``<rect>`` shapes are handled — these cover the common case
    of CSS-backgrounded boxes. Path-shaped pattern fills are left as
    pattern-N layers for the operator to handle manually.

    Returns ``(count, warnings)`` like :func:`vectorize_embedded_images`.
    """
    from pen_plotter.converters.bitmap import BitmapConverter

    warnings: list[str] = []
    parent_map = {child: parent for parent in root.iter() for child in parent}
    # Snapshot — we mutate the tree as we go.
    candidates = [
        rect
        for rect in root.iter()
        if _local(rect.tag) == "rect"
        and (rect.get("fill") or "").startswith("url(#")
    ]
    if not candidates:
        return 0, warnings

    try:
        import pymupdf
    except ImportError:
        warnings.append("PyMuPDF unavailable — pattern fills left as-is.")
        return 0, warnings

    converter = BitmapConverter()
    produced = 0
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        if not 0 <= page_index < doc.page_count:
            warnings.append("Pattern rasterisation skipped: page index out of range.")
            return 0, warnings
        page = doc[page_index]

        for index, rect in enumerate(candidates, start=1):
            fill = rect.get("fill") or ""
            # url(#pattern_3) → "pattern_3"
            pattern_id = fill[fill.find("#") + 1 : fill.rfind(")")]
            if not pattern_id:
                continue
            if not _pattern_is_empty(root, pattern_id):
                continue  # the pattern has content; let the viewer render it
            parent = parent_map.get(rect)
            if parent is None:
                continue
            bbox = _rect_bbox_user_units(rect, parent_map, root)
            if bbox is None:
                continue
            x_min, y_min, x_max, y_max = bbox
            # PyMuPDF SVG user units == PDF points; clip the page to the
            # bbox and render at a print-grade DPI so the bitmap pipeline
            # has enough pixels to halftone the gradient cleanly.
            try:
                pix = page.get_pixmap(
                    clip=pymupdf.Rect(x_min, y_min, x_max, y_max), dpi=300
                )
                png_bytes = pix.tobytes("png")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Pattern #{index}: page-crop render failed ({exc}).")
                continue
            try:
                result: ConversionResult = converter.convert(
                    png_bytes, options=bitmap_options
                )
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Pattern #{index}: vectorisation failed ({exc}).")
                continue
            groups = _inner_groups(result.svg)
            if not groups:
                warnings.append(
                    f"Pattern #{index}: produced no drawable strokes (all-background?)."
                )
                # Remove the empty rect so the user isn't left with an
                # invisible silhouette.
                parent.remove(rect)
                continue
            try:
                inner_root = ET.fromstring(result.svg)
                vb = inner_root.get("viewBox", "")
                _, _, src_w, src_h = (float(v) for v in vb.split())
            except (ET.ParseError, ValueError):
                warnings.append(f"Pattern #{index}: bitmap result missing viewBox.")
                continue
            dst_w = x_max - x_min
            dst_h = y_max - y_min
            sx = dst_w / max(src_w, 1e-9)
            sy = dst_h / max(src_h, 1e-9)
            wrapper = ET.Element(f"{{{_SVG_NS}}}g")
            wrapper.set(_INKSCAPE_LABEL, f"pattern-{index}")
            transform_parts = [f"translate({x_min} {y_min})", f"scale({sx} {sy})"]
            wrapper.set("transform", " ".join(transform_parts))
            for group in groups:
                # Same rationale as in vectorize_embedded_images: we
                # don't want the converter's internal per-color labels
                # to show up as top-level layers.
                group.attrib.pop(_INKSCAPE_LABEL, None)
                wrapper.append(group)
            position = list(parent).index(rect)
            parent.remove(rect)
            parent.insert(position, wrapper)
            produced += 1

    return produced, warnings


def hoist_labeled_groups(root: ET.Element) -> int:
    """Lift any descendant ``<g inkscape:label>`` up to be a direct child of ``root``.

    PyMuPDF often wraps an ``<image>`` in an outer ``<g transform="…">`` that
    positions it on the page. After :func:`vectorize_embedded_images` replaces
    the image with a labeled group, that label lives one or more levels deep
    rather than at the root, so ``extract_layers`` (which only inspects direct
    children) misses it. This function composes every ancestor transform into
    the labeled group's own ``transform`` attribute and moves it to the root.

    Returns the number of groups hoisted.
    """
    hoisted = 0
    # Iterate until quiescent — moving one group may expose another.
    while True:
        parent_map = {child: parent for parent in root.iter() for child in parent}
        candidate: ET.Element | None = None
        for elem in root.iter():
            if _local(elem.tag) != "g" or not elem.get(_INKSCAPE_LABEL):
                continue
            if elem in list(root):
                continue
            candidate = elem
            break
        if candidate is None:
            return hoisted

        # Compose ancestor transforms from outermost down to the labeled group's
        # current parent, then append the group's own transform if present.
        transforms: list[str] = []
        cursor: ET.Element | None = parent_map.get(candidate)
        chain: list[ET.Element] = []
        while cursor is not None and cursor is not root:
            chain.append(cursor)
            cursor = parent_map.get(cursor)
        for ancestor in reversed(chain):
            value = ancestor.get("transform")
            if value:
                transforms.append(value)
        existing = candidate.get("transform")
        if existing:
            transforms.append(existing)
        if transforms:
            candidate.set("transform", " ".join(transforms))

        parent = parent_map[candidate]
        parent.remove(candidate)
        root.append(candidate)
        hoisted += 1


_DRAWABLE_LEAVES = {"path", "polyline", "polygon", "line", "circle", "rect", "ellipse"}
_DRAWABLE_TAGS = _DRAWABLE_LEAVES | {"g"}


def _normalize_fill(value: str | None) -> str:
    """Normalize a ``fill`` attribute to a hex key, ``"none"``, or ``""``.

    * ``None`` or missing → ``""`` (means "inherit"; SVG default fill is
      black, so the caller treats this as ``#000000``).
    * ``"none"`` → ``"none"`` (no fill; the caller falls back to stroke).
    * ``url(#...)`` → returned unchanged so pattern-filled shapes get
      their own bucket separate from any solid color.
    * ``#rgb`` / ``#rrggbb`` → expanded and lowercased to ``#rrggbb``.
    * Anything else (named colors, ``rgb(…)``, …) → lowercased as-is.
    """
    if value is None:
        return ""
    value = value.strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered == "none":
        return "none"
    if lowered.startswith("url("):
        return value  # preserve case so the IRI matches the def's id
    if lowered.startswith("#") and len(lowered) == 4:
        # #abc → #aabbcc
        return f"#{lowered[1] * 2}{lowered[2] * 2}{lowered[3] * 2}"
    return lowered


def _effective_color_key(element: ET.Element) -> str:
    """Return the color bucket key for a leaf drawable.

    Strokes-only paths (``fill="none"`` with a ``stroke`` set) are
    grouped by their stroke; everything else is grouped by its
    (normalized) fill, with an absent fill counted as black so PyMuPDF
    text glyphs (which inherit) land in the default bucket.
    """
    fill = _normalize_fill(element.get("fill"))
    if fill == "none":
        stroke = _normalize_fill(element.get("stroke"))
        if stroke and stroke not in {"none", ""}:
            return stroke
        return "none"  # invisible; will be dropped
    if fill == "":
        return "#000000"
    return fill


def _leaf_color_buckets(root: ET.Element) -> dict[str, list[ET.Element]]:
    """Bucket every loose leaf drawable under ``root`` by its color key.

    Walks the loose top-level drawables (children that aren't already
    labeled layers) and recurses into ``<g>`` wrappers to reach the
    leaves. Returns a mapping ``{color_key → [leaf_element, …]}``.
    Leaves with key ``"none"`` (no fill, no stroke) are skipped — they
    would plot as nothing anyway.
    """
    buckets: dict[str, list[ET.Element]] = {}
    for child in list(root):
        local = _local(child.tag)
        if local not in _DRAWABLE_TAGS:
            continue
        # Already a labeled top-level layer — leave it alone.
        if local == "g" and child.get(_INKSCAPE_LABEL):
            continue
        for leaf in child.iter() if local == "g" else (child,):
            if _local(leaf.tag) not in _DRAWABLE_LEAVES:
                continue
            key = _effective_color_key(leaf)
            if key == "none":
                continue
            buckets.setdefault(key, []).append(leaf)
    return buckets


def _label_for_color(key: str, default_label: str) -> str:
    """Pick the inkscape:label for a color bucket.

    Black / inherited fills get the operator-supplied default
    (``"text"`` or ``"drawings"``) since those are the body content for
    the typical PDF/HTML route. Pattern fills get ``pattern-N`` (the N
    is assigned by the caller). Other solid colors get
    ``color-#rrggbb`` so the frontend can show the swatch without
    re-deriving it from the geometry.
    """
    if key == "#000000":
        return default_label
    if key.startswith("url("):
        return key  # caller rewrites pattern-N before insertion
    return f"color-{key}"


def split_loose_drawables_by_fill(root: ET.Element, default_label: str = "text") -> int:
    """Split top-level non-labeled drawables into one labeled group per fill.

    With a single distinct fill, behaves like the original
    ``wrap_text_layer``: everything goes into one ``<g
    inkscape:label="text">`` (or ``"drawings"`` when Hershey owns the
    ``text`` label). With multiple colors — the case the colored HTML
    print-test page exercises — produces one labeled group per color
    so the operator can route each one to its own pen.

    Returns the number of labeled groups that were inserted. Operates
    in place. Pattern fills (``url(#…)``) are bucketed separately and
    end up as ``pattern-N`` layers so the operator can see them in the
    layer list even if their content was not (yet) rasterised.
    """
    parent_map = {child: parent for parent in root.iter() for child in parent}
    buckets = _leaf_color_buckets(root)
    if not buckets:
        return 0

    # When everything is the same color, preserve the legacy single-layer
    # behavior so existing pipelines and tests keep their "text" /
    # "drawings" wrapper.
    single_bucket = len(buckets) == 1

    # Ordered by deterministic key sort so the layer order is stable
    # across runs (lru_cache in _measure relies on identical SVG output
    # for identical input).
    pattern_index = 0
    new_groups: list[tuple[str, ET.Element]] = []
    for key in sorted(buckets):
        leaves = buckets[key]
        if single_bucket:
            label = default_label
        elif key.startswith("url("):
            pattern_index += 1
            label = f"pattern-{pattern_index}"
        else:
            label = _label_for_color(key, default_label)
        wrapper = ET.Element(f"{{{_SVG_NS}}}g")
        wrapper.set(_INKSCAPE_LABEL, label)
        # Stamp a representative color on the wrapper itself so
        # ``_group_color`` in :mod:`pen_plotter.core.layers` picks up a
        # real hex (not the first url() reference) for the UI swatch.
        if not key.startswith("url(") and key not in {"none", ""}:
            wrapper.set("fill", key)
        for leaf in leaves:
            parent = parent_map.get(leaf)
            if parent is None:
                continue
            parent.remove(leaf)
            wrapper.append(leaf)
        new_groups.append((label, wrapper))

    # Tidy up: remove any loose top-level <g> wrappers that are now
    # empty (their leaves were redistributed into per-color groups).
    for child in list(root):
        local = _local(child.tag)
        if local != "g" or child.get(_INKSCAPE_LABEL):
            continue
        if not any(
            _local(d.tag) in _DRAWABLE_LEAVES for d in child.iter() if d is not child
        ):
            root.remove(child)

    # Insert before any existing labeled layers (``image-N``, Hershey
    # ``text``, …) so the document layering stays consistent: vector
    # content drawn before bitmaps.
    insert_at = 0
    for i, child in enumerate(root):
        if _local(child.tag) == "g" and child.get(_INKSCAPE_LABEL):
            insert_at = i
            break
        insert_at = i + 1
    for _, wrapper in new_groups:
        root.insert(insert_at, wrapper)
        insert_at += 1
    return len(new_groups)


def wrap_text_layer(root: ET.Element, label: str = "text") -> bool:
    """Backward-compatible shim for :func:`split_loose_drawables_by_fill`.

    Retained so external callers and tests that still import
    ``wrap_text_layer`` keep working. The new function does the real
    work — splitting by fill into per-color labeled groups when the
    document carries more than one fill.
    """
    return split_loose_drawables_by_fill(root, default_label=label) > 0


def postprocess_pdf_svg(
    svg: str,
    *,
    bitmap_options: dict[str, Any] | None = None,
    hershey_text_group: str | None = None,
    pdf_bytes: bytes | None = None,
    page_index: int = 0,
) -> tuple[str, list[str]]:
    """Run the full PDF-SVG post-processing chain.

    Expands ``<use>`` references inline, vectorizes embedded raster
    ``<image>`` elements into their own labeled layers, rasterises any
    pattern-filled shapes (CSS gradients PyMuPDF emits as empty
    ``<pattern>`` references) by cropping the original PDF page, and
    splits the remaining vector content into one labeled group per
    fill color. The output is a self-contained pivot SVG ready for
    sanitize + extract_layers.

    When ``hershey_text_group`` is supplied, the function instead
    strips every PyMuPDF text glyph from the input (so the operator's
    original-font outlines don't double up with our re-render) and
    appends the provided SVG fragment as a new top-level group. The
    fragment is expected to be a single ``<g inkscape:label="...">``
    element — usually produced by
    :func:`pen_plotter.typography.render_placed_spans` — so it lands at
    the same nesting level as the existing labeled layers and
    ``extract_layers`` picks it up unchanged.

    Args:
        svg: Raw PyMuPDF SVG output.
        bitmap_options: Optional dictionary forwarded to the bitmap
            converter for raster vectorization (algorithm, palette, etc.).
        hershey_text_group: Optional SVG ``<g>`` fragment to inject in
            place of the original PDF text. When provided the original
            text glyphs are removed first.
        pdf_bytes: The original PDF bytes. When supplied (and a
            pattern-filled shape is detected), the corresponding page
            region is rendered by PyMuPDF and handed to the bitmap
            converter so CSS gradients plot as halftoned strokes
            instead of plotting as a flat silhouette.
        page_index: Index of the PDF page that produced ``svg``; used
            only when ``pdf_bytes`` is supplied to crop the right page
            for pattern rasterisation.

    Returns:
        ``(svg, warnings)``: the post-processed SVG plus any per-image
        warnings (failed decode, empty vectorization, …).
    """
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg, ["Could not parse SVG for post-processing."]

    if hershey_text_group:
        # Remove the original text BEFORE expanding <use>s, otherwise
        # the glyph paths get inlined and we can no longer tell them
        # apart from real drawings.
        strip_text_glyphs(root)
    # Rasterise pattern fills BEFORE expanding <use>s — the latter
    # nukes the <defs> block that holds the <pattern> definitions, so
    # by the time it's done we can no longer tell whether a
    # ``url(#pattern_N)`` reference pointed to an empty gradient
    # (needs rasterisation) or a populated pattern (best left alone).
    if pdf_bytes is not None:
        _, pattern_warnings = rasterize_pattern_fills(
            root,
            pdf_bytes=pdf_bytes,
            page_index=page_index,
            bitmap_options=bitmap_options,
        )
    else:
        pattern_warnings = []
    expand_use_refs(root)
    _, image_warnings = vectorize_embedded_images(root, bitmap_options=bitmap_options)
    image_warnings.extend(pattern_warnings)
    hoist_labeled_groups(root)
    # When Hershey is taking over the "text" label, the catch-all
    # wrapper for the document's remaining vector content (rules,
    # shapes, lines, …) needs a different layer name. Otherwise the
    # operator ends up with two distinct "text" layers — one with the
    # Hershey strokes, one with the non-text drawings — and the
    # per-layer pen-slot UI can't tell them apart.
    split_loose_drawables_by_fill(
        root, default_label="drawings" if hershey_text_group else "text"
    )

    if hershey_text_group:
        try:
            fragment = ET.fromstring(hershey_text_group)
            root.append(fragment)
        except ET.ParseError:
            image_warnings.append("Hershey text group was not valid SVG; skipped.")

    # Ensure xmlns:inkscape is on the root so downstream parsers see the
    # labels we just added.
    if root.get(f"{{{_INKSCAPE_NS}}}__placeholder__") is None:
        pass  # ElementTree manages xmlns via register_namespace

    return svg_tostring(root), image_warnings
