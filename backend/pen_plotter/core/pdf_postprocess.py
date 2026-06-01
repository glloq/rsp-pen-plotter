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
import math
import re
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
        # Keep the block only if a child lacks an ``id`` (we cannot prove it was
        # a consumed glyph, so we err on the side of preserving it).
        keep = any(not child.get("id") for child in defs)
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


def _ancestor_transforms_to_root(
    start: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
    root: ET.Element,
) -> list[str]:
    """Collect every ``transform`` attribute walking ``start`` up to ``root``.

    Returned in outermost-first order so ``" ".join(...)`` produces the
    SVG-correct composed transform string when applied to a wrapper
    around the original leaf.
    """
    chain: list[ET.Element] = []
    cursor: ET.Element | None = start
    while cursor is not None and cursor is not root:
        chain.append(cursor)
        cursor = parent_map.get(cursor)
    transforms: list[str] = []
    for ancestor in reversed(chain):
        value = ancestor.get("transform")
        if value:
            transforms.append(value)
    return transforms


def _apply_affine(
    matrix: tuple[float, float, float, float, float, float],
    points: list[tuple[float, float]],
) -> tuple[float, float, float, float] | None:
    """Apply a 2x3 affine to ``points`` and return their AABB.

    Returns ``None`` if ``points`` is empty.
    """
    if not points:
        return None
    a, b, c, d, e, f = matrix
    xs = [a * px + c * py + e for px, py in points]
    ys = [b * px + d * py + f for px, py in points]
    return min(xs), min(ys), max(xs), max(ys)


def _composed_transform(
    element: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
    root: ET.Element,
) -> tuple[float, float, float, float, float, float]:
    """Return ancestor transforms composed with the element's own."""
    a1, b1, c1, d1, e1, f1 = _ancestor_transform(element, parent_map, root)
    a2, b2, c2, d2, e2, f2 = _parse_transform(element.get("transform"))
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


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
    corners = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
    return _apply_affine(_composed_transform(rect, parent_map, root), corners)


def _path_bbox_user_units(
    path: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
    root: ET.Element,
) -> tuple[float, float, float, float] | None:
    """Return the AABB of a ``<path>`` element in user units.

    WeasyPrint emits CSS-styled boxes (``background-color`` divs,
    color-bar swatches) as ``<path>`` elements whose ``d`` string is a
    plain orthogonal rectangle ``M x y H x2 V y2 H x V y Z``. We parse
    every numeric pair the path touches — that's a strict superset of
    those corners and gives the right AABB even when WeasyPrint
    inserts intermediate ``L`` segments for rounded-border decoration.
    """
    d = path.get("d") or ""
    if not d:
        return None

    # Pull every numeric literal out of the d-string. SVG paths use
    # commands (M / L / H / V / C / Z …) but for an AABB we only care
    # about the coordinates each command consumes; the absolute /
    # relative distinction doesn't matter when the path is closed and
    # we just want the extreme points reached along it.
    # SVG number grammar: optional sign, then EITHER ``digits[.digits]``
    # OR ``.digits`` — PyMuPDF emits glyph d-strings with no leading
    # zero (e.g. ``.61035158``), so a regex that requires a digit
    # before the decimal point silently splits ``.61035158`` into
    # nothing-then-``61035158``, producing astronomical bbox values
    # and bogging the hatcher down in millions of phantom hatch lines.
    _number_re = r"-?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
    nums = [float(t) for t in re.findall(_number_re, d)]
    if len(nums) < 2:
        return None
    # Walk through commands accumulating the current pen position so
    # that ``H``/``V`` (which only carry one number per step) produce
    # the right second coordinate.
    points: list[tuple[float, float]] = []
    tokens = re.findall(rf"[a-zA-Z]|{_number_re}", d)
    cx = cy = 0.0
    i = 0
    cmd = ""
    rel = False
    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok.upper()
            rel = tok.islower()
            i += 1
            if cmd == "Z":
                continue
            continue
        if not cmd:
            i += 1
            continue
        try:
            if cmd in {"M", "L", "T"}:
                x, y = float(tokens[i]), float(tokens[i + 1])
                cx, cy = (cx + x, cy + y) if rel else (x, y)
                points.append((cx, cy))
                i += 2
                # subsequent pairs after M are L
                if cmd == "M":
                    cmd = "L"
            elif cmd == "H":
                x = float(tokens[i])
                cx = cx + x if rel else x
                points.append((cx, cy))
                i += 1
            elif cmd == "V":
                y = float(tokens[i])
                cy = cy + y if rel else y
                points.append((cx, cy))
                i += 1
            elif cmd in {"C"}:
                # Cubic — sample all three points (control1, control2, end).
                for _ in range(3):
                    x, y = float(tokens[i]), float(tokens[i + 1])
                    px, py = (cx + x, cy + y) if rel else (x, y)
                    points.append((px, py))
                    i += 2
                cx, cy = points[-1]
            elif cmd in {"S", "Q"}:
                for _ in range(2):
                    x, y = float(tokens[i]), float(tokens[i + 1])
                    px, py = (cx + x, cy + y) if rel else (x, y)
                    points.append((px, py))
                    i += 2
                cx, cy = points[-1]
            elif cmd == "A":
                # Skip flags/rx/ry, take the endpoint.
                i += 5  # rx, ry, x-axis-rot, large-arc-flag, sweep-flag
                x, y = float(tokens[i]), float(tokens[i + 1])
                cx, cy = (cx + x, cy + y) if rel else (x, y)
                points.append((cx, cy))
                i += 2
            else:
                i += 1
        except (IndexError, ValueError):
            return None
    return _apply_affine(_composed_transform(path, parent_map, root), points)


def _has_visible_content(subtree: ET.Element) -> bool:
    """Return ``True`` if ``subtree`` has any ink-bearing leaf outside a mask.

    Paths buried inside a ``<clipPath>`` or ``<mask>`` define the mask
    region itself — they do not paint pixels and so don't count as
    "visible content". Same for anything still hiding in a ``<defs>``
    block that was inlined as part of an ``<use>`` expansion.

    Pure-white fills (PyMuPDF inserts a ``<rect fill="white">`` as the
    background of every emitted shading pattern) don't count either:
    they paint no visible ink on a white page and would otherwise mask
    a CSS gradient / grid pattern that the operator expects to plot.
    """
    masked = {f"{{{_SVG_NS}}}clipPath", f"{{{_SVG_NS}}}mask", f"{{{_SVG_NS}}}defs"}
    white_fills = {"white", "#fff", "#ffffff", "rgb(255,255,255)"}
    stack: list[ET.Element] = [subtree]
    while stack:
        node = stack.pop()
        if node.tag in masked:
            continue
        if node is not subtree and _local(node.tag) in _DRAWABLE_LEAVES:
            fill = (node.get("fill") or "").strip().lower()
            stroke = (node.get("stroke") or "").strip().lower()
            # Default SVG fill is black; only an explicit ``none`` /
            # ``white`` suppresses ink. A non-white stroke also counts.
            fill_paints = fill not in {"none", *white_fills} if fill else True
            stroke_paints = bool(stroke) and stroke not in {"none", *white_fills}
            if fill_paints or stroke_paints:
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


def _is_renderable_solid_fill(value: str) -> bool:
    """Return ``True`` if ``fill`` is a solid color worth rasterising.

    Skips ``none``, pattern references, the SVG default of black-without-
    explicit-fill (we'd rasterise every glyph), and pure white (page
    background that would produce no strokes after the BitmapConverter
    drops it). Greys are intentionally excluded too — they get a
    cheaper density-modulated hatching pass in
    :func:`apply_grayscale_density_hatching`, which folds every shade
    into one black layer instead of producing one ``color-#nnnnnn``
    layer per swatch on a printer-test grayscale ramp.
    """
    if not value:
        return False
    v = value.strip().lower()
    if v in {"none", "transparent", "white", "#fff", "#ffffff", "rgb(255,255,255)"}:
        return False
    if v.startswith("url("):
        return False
    if v in {"black", "#000", "#000000", "rgb(0,0,0)"}:
        # Pure black is almost always text-ink, page-frame strokes, or
        # alignment marks. Leaving them as vector outlines keeps glyphs
        # legible and registration crosses crisp; rasterising them would
        # turn every black box into a fully-hatched silhouette.
        return False
    # Skip the greys — they belong to the grayscale-density path.
    is_gray, _ = _parse_grayscale_hex(v)
    if is_gray:
        return False
    return True


def _parse_grayscale_hex(value: str) -> tuple[bool, int]:
    """Parse a fill string as a grayscale hex; return ``(is_gray, channel)``.

    ``channel`` is the 0..255 grey level when ``is_gray`` is true,
    so the caller can compute darkness without re-parsing. Returns
    ``(False, 0)`` for any non-grey color, ``url(…)``, named colors
    other than ``black``/``white``/``gray``, or unparsable input.
    """
    v = value.strip().lower()
    if not v:
        return False, 0
    if v == "black":
        return True, 0
    if v == "white":
        return True, 255
    if v == "gray" or v == "grey":
        return True, 128
    if v.startswith("rgb("):
        try:
            parts = [int(p.strip()) for p in v[4:-1].split(",")]
        except ValueError:
            return False, 0
        if len(parts) == 3 and parts[0] == parts[1] == parts[2]:
            return True, parts[0]
        return False, 0
    if not v.startswith("#"):
        return False, 0
    if len(v) == 4:  # #abc
        r, g, b = v[1] * 2, v[2] * 2, v[3] * 2
    elif len(v) == 7:  # #aabbcc
        r, g, b = v[1:3], v[3:5], v[5:7]
    else:
        return False, 0
    try:
        ri, gi, bi = int(r, 16), int(g, 16), int(b, 16)
    except ValueError:
        return False, 0
    if ri == gi == bi:
        return True, ri
    return False, 0


def _hatch_lines_for_bbox(
    bbox: tuple[float, float, float, float],
    angle_rad: float,
    spacing: float,
) -> list[tuple[float, float, float, float]]:
    """Return ``[(x1, y1, x2, y2), …]`` for hatch lines clipped to ``bbox``.

    Lines run parallel to ``angle_rad`` and step ``spacing`` apart along
    the perpendicular direction; both numbers are in the same units as
    ``bbox``. Each returned tuple is the entry/exit point of one line
    against the rectangle's edges so a downstream SVG writer can emit
    one ``<path d="M x1 y1 L x2 y2"/>`` per tuple without further
    clipping.
    """
    x_min, y_min, x_max, y_max = bbox
    if spacing <= 0 or x_max <= x_min or y_max <= y_min:
        return []
    dx, dy = math.cos(angle_rad), math.sin(angle_rad)
    nx, ny = -dy, dx  # perpendicular
    # Project the four corners onto the perpendicular axis so we know
    # the range of distances ``d`` the hatching needs to cover.
    corners = [(x_min, y_min), (x_max, y_min), (x_min, y_max), (x_max, y_max)]
    projections = [px * nx + py * ny for px, py in corners]
    d_min, d_max = min(projections), max(projections)
    # Snap to a multiple of spacing for a stable phase across nearby
    # rectangles (otherwise abutting swatches show a seam where the
    # hatching shifts).
    d_start = math.floor(d_min / spacing) * spacing

    lines: list[tuple[float, float, float, float]] = []
    eps = 1e-9
    d = d_start
    while d <= d_max + eps:
        intersections: list[tuple[float, float]] = []
        # Each rectangle edge: parameterise the infinite hatch line as
        # P(t) = d * (nx, ny) + t * (dx, dy) and solve for the t that
        # hits each edge.
        if abs(dx) > eps:
            for x_edge in (x_min, x_max):
                t = (x_edge - d * nx) / dx
                y = d * ny + t * dy
                if y_min - eps <= y <= y_max + eps:
                    intersections.append((x_edge, max(y_min, min(y_max, y))))
        if abs(dy) > eps:
            for y_edge in (y_min, y_max):
                t = (y_edge - d * ny) / dy
                x = d * nx + t * dx
                if x_min - eps <= x <= x_max + eps:
                    intersections.append((max(x_min, min(x_max, x)), y_edge))
        if len(intersections) >= 2:
            # Take the two most distant intersections — corners can show
            # up twice when the line grazes a vertex.
            best = (intersections[0], intersections[1])
            best_d2 = (best[0][0] - best[1][0]) ** 2 + (best[0][1] - best[1][1]) ** 2
            for i in range(len(intersections)):
                for j in range(i + 1, len(intersections)):
                    p, q = intersections[i], intersections[j]
                    d2 = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                    if d2 > best_d2:
                        best, best_d2 = (p, q), d2
            if best_d2 > eps:
                lines.append((best[0][0], best[0][1], best[1][0], best[1][1]))
        d += spacing
    return lines


def _path_is_outline_frame(path: ET.Element) -> bool:
    """Return ``True`` if a ``<path>`` is a hollow frame, not a solid fill.

    WeasyPrint emits a CSS ``border`` as a single path with two nested
    rectangle subpaths and ``fill-rule="evenodd"`` — the painted area
    is only the thin ring between them, but the AABB the hatcher
    computes is the OUTER rectangle. Hatching that AABB then fills the
    entire interior with hatch lines, which on a ``.text-line``
    print-test row paints across the small text glyph sitting inside
    the border and the operator sees the text "barred". We detect the
    frame shape by either of two signals — both are cheap and PyMuPDF
    / WeasyPrint set them consistently:

    * ``fill-rule="evenodd"`` or ``clip-rule="evenodd"`` on the path
      (the only reason to set this is to carve a hole out of the fill).
    * More than one absolute ``M`` command in ``d`` (multiple
      subpaths — typically the outer ring + inner ring of a border /
      frame, or a glyph with a counter, neither of which we want to
      bbox-hatch).

    Frame paths fall back to plotting as their original outline (the
    sanitized SVG keeps the path itself), which on a 1-pt border is
    what the operator visually expects.
    """
    if (path.get("fill-rule") or "").strip().lower() == "evenodd":
        return True
    if (path.get("clip-rule") or "").strip().lower() == "evenodd":
        return True
    d = path.get("d") or ""
    if not d:
        return False
    # Count absolute moveto commands. A single ``M`` opens the only
    # subpath; two or more means the path closes one ring and opens
    # another — the hallmark of a border / counter / compound shape.
    return d.count("M") + d.count("m") > 1


def _collect_text_glyph_positions(
    root: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
) -> list[tuple[float, float]]:
    """Return every text-glyph origin in document user-unit coords.

    PyMuPDF emits each PDF text glyph as
    ``<use data-text="X" xlink:href="#font_..." transform="matrix(a 0
    0 d x y)"/>``, where ``(x, y)`` is the glyph baseline origin in
    the local coordinate space. To compare against the AABBs the
    hatchers compute (already composed up to root) we apply every
    ancestor transform on the way back up. The returned points feed
    :func:`_bbox_contains_text` so the hatch passes can leave any
    shape that surrounds text alone — bbox-hatching such a shape
    would paint hatch lines across the text glyphs and the operator
    reads the result as "text barred".
    """
    positions: list[tuple[float, float]] = []
    for elem in root.iter():
        if _local(elem.tag) != "use":
            continue
        href = (
            elem.get("href")
            or elem.get(_XLINK_HREF)
            or elem.get("xlink:href")
            or ""
        ).lstrip("#")
        is_text = elem.get("data-text") is not None or href.startswith("font_")
        if not is_text:
            continue
        transform = elem.get("transform") or ""
        # PyMuPDF only ever emits ``matrix(a b c d e f)`` for text
        # glyphs; pull (e, f) directly. Fall back to translate(x, y)
        # for safety in case a future version switches forms.
        local_x = 0.0
        local_y = 0.0
        m = re.search(r"matrix\(([^)]+)\)", transform)
        if m:
            nums = [
                float(v) for v in re.split(r"[\s,]+", m.group(1).strip()) if v
            ]
            if len(nums) == 6:
                local_x, local_y = nums[4], nums[5]
        else:
            m = re.search(r"translate\(([^)]+)\)", transform)
            if m:
                nums = [
                    float(v) for v in re.split(r"[\s,]+", m.group(1).strip()) if v
                ]
                if len(nums) >= 1:
                    local_x = nums[0]
                if len(nums) >= 2:
                    local_y = nums[1]
            else:
                try:
                    local_x = float(elem.get("x", "0"))
                    local_y = float(elem.get("y", "0"))
                except ValueError:
                    pass
        a, b, c, d, e, f = _ancestor_transform(elem, parent_map, root)
        page_x = a * local_x + c * local_y + e
        page_y = b * local_x + d * local_y + f
        positions.append((page_x, page_y))
    return positions


def _bbox_contains_text(
    bbox: tuple[float, float, float, float],
    text_positions: list[tuple[float, float]],
) -> bool:
    """``True`` if any text glyph origin sits inside ``bbox``."""
    x_min, y_min, x_max, y_max = bbox
    for tx, ty in text_positions:
        if x_min <= tx <= x_max and y_min <= ty <= y_max:
            return True
    return False


def apply_grayscale_density_hatching(
    root: ET.Element,
    *,
    min_spacing_pt: float = 0.85,  # ~0.3 mm @ 72 dpi
    max_spacing_pt: float = 8.5,  # ~3.0 mm
    min_area_pt2: float = 50.0,
    stroke_width_pt: float = 0.8,  # ~0.28 mm pen
) -> int:
    """Fold grayscale-filled shapes into one density-modulated black layer.

    On a printer-test page with a grayscale ramp the per-color split
    produces one ``color-#nnnnnn`` layer per grey shade — twelve
    layers for a CMYKRGB + 11-bar grey ramp that the operator then
    has to manually route onto a single black pen. This helper takes
    every ``<rect>`` / ``<path>`` whose fill is grey (R==G==B, not
    pure black or white) and replaces it with crossed hatching
    (``+45°`` × ``-45°``) whose stroke spacing scales inversely with
    the shade's darkness: ``#1a1a1a`` (90 % ink) gets dense hatching,
    ``#e6e6e6`` (10 % ink) gets sparse hatching, ``#808080`` lands in
    between. All hatches land in one ``<g inkscape:label="grayscale"
    stroke="#000000">`` so the operator binds the whole grey ramp to
    one pen with one click.

    Pure black is left alone (handled as ``text`` ink elsewhere) and
    shapes below ``min_area_pt2`` are skipped (border slivers, text
    underlines) so the helper doesn't sprinkle hatching across decorative
    rules.

    Returns the number of shapes replaced.
    """
    parent_map = {child: parent for parent in root.iter() for child in parent}
    text_positions = _collect_text_glyph_positions(root, parent_map)
    candidates: list[tuple[ET.Element, int, tuple[float, float, float, float]]] = []
    for shape in list(root.iter()):
        local = _local(shape.tag)
        if local not in {"rect", "path"}:
            continue
        fill = shape.get("fill") or ""
        is_gray, value = _parse_grayscale_hex(fill)
        if not is_gray:
            continue
        if value >= 255:
            continue  # pure white — page background, paints no ink anyway.
        # Pure black (value == 0) is admitted here so the operator's
        # rgb(0,0,0) swatch in the printer-test page plots as solid
        # hatching at min spacing. ``HtmlConverter`` rewrites every
        # explicit ``background-color:#000`` to ``#010101`` before
        # WeasyPrint runs so the path actually carries a hex value
        # (without that nudge WeasyPrint emits black as the SVG
        # default and leaves the path with no ``fill`` attribute,
        # indistinguishable from the many auxiliary no-fill paths it
        # also emits for borders / clips / overlays).
        if local == "path" and _path_is_outline_frame(shape):
            # Border / frame path — bbox-hatching would paint inside
            # the ring and bar any text the border surrounds.
            continue
        if local == "rect":
            bbox = _rect_bbox_user_units(shape, parent_map, root)
        else:
            bbox = _path_bbox_user_units(shape, parent_map, root)
        if bbox is None:
            continue
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        if area < min_area_pt2:
            continue
        if _bbox_contains_text(bbox, text_positions):
            # The shape encloses text glyphs (e.g. a CSS-styled callout
            # box with a paragraph inside, or any background that
            # surrounds rendered text). Hatching its bbox paints
            # parallel lines across the glyphs the operator wants
            # readable — so leave the shape as-is and let it plot as
            # its outline instead.
            continue
        candidates.append((shape, value, bbox))

    if not candidates:
        return 0


    hatch_group = ET.Element(f"{{{_SVG_NS}}}g")
    hatch_group.set(_INKSCAPE_LABEL, "grayscale")
    hatch_group.set("stroke", "#000000")
    hatch_group.set("fill", "none")
    hatch_group.set("stroke-width", f"{stroke_width_pt:.3f}")

    replaced = 0
    for shape, value, bbox in candidates:
        darkness = 1.0 - value / 255.0
        # Inverse: darker → smaller spacing → denser mesh. A linear
        # ramp matches the operator's intuition that swapping a swatch
        # one notch darker should add roughly the same amount of ink
        # at every shade — non-linear feels surprisingly dim at the
        # midtones.
        spacing = max_spacing_pt - darkness * (max_spacing_pt - min_spacing_pt)
        for angle_deg in (45.0, -45.0):
            for x1, y1, x2, y2 in _hatch_lines_for_bbox(
                bbox, math.radians(angle_deg), spacing
            ):
                path_el = ET.Element(f"{{{_SVG_NS}}}path")
                path_el.set("d", f"M{x1:.3f} {y1:.3f}L{x2:.3f} {y2:.3f}")
                hatch_group.append(path_el)
        parent = parent_map.get(shape)
        if parent is not None:
            parent.remove(shape)
        replaced += 1

    if replaced:
        _insert_background_layer(root, hatch_group)
    return replaced


def _insert_background_layer(root: ET.Element, group: ET.Element) -> None:
    """Insert ``group`` at the page-background z-position of ``root``.

    PyMuPDF emits backgrounds before text in document order so that text
    glyphs render on top of any coloured fill. Density-hatching layers
    represent those backgrounds, so they need to inherit that bottom
    z-position — otherwise the hatch lines paint over the text and the
    operator reads the result as "text struck through". Insert after
    any leading ``<defs>`` block (which is non-rendering anyway) but
    before the first drawable child.
    """
    insert_at = 0
    for i, child in enumerate(root):
        if _local(child.tag) == "defs":
            insert_at = i + 1
            continue
        break
    root.insert(insert_at, group)


def _luminance_0_1(hex_color: str) -> float:
    """ITU-R BT.601 luma for a ``#rrggbb`` string in 0..1 range."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def apply_color_density_hatching(
    root: ET.Element,
    *,
    min_spacing_pt: float = 0.85,
    max_spacing_pt: float = 8.5,
    min_area_pt2: float = 50.0,
    stroke_width_pt: float = 0.8,
) -> int:
    """Fold solid-colored filled shapes into per-colour density-hatched layers.

    For every ``<rect>`` / ``<path>`` whose fill is a renderable solid
    colour (non-black, non-grey, non-white, non-pattern), produce
    crossed hatching (``+45°`` × ``-45°``) in the shape's own colour
    and group every hatch line for that colour into a single
    ``<g inkscape:label="color-#rrggbb" stroke="#rrggbb">``. Hatch
    spacing scales inversely with the colour's luminance — a saturated
    red hatches denser than a pale yellow — so the operator gets a
    plotted-looking fill out of the box on a CMYKRGB HTML / PDF test
    page instead of the bare potrace outline that
    :func:`rasterize_solid_color_fills` produces by default. Greys are
    handled by :func:`apply_grayscale_density_hatching` and pure black /
    white are deliberately skipped (text ink, page background).

    Returns the number of shapes replaced.
    """
    parent_map = {child: parent for parent in root.iter() for child in parent}
    text_positions = _collect_text_glyph_positions(root, parent_map)
    buckets: dict[str, list[tuple[ET.Element, tuple[float, float, float, float]]]] = {}
    for shape in list(root.iter()):
        local = _local(shape.tag)
        if local not in {"rect", "path"}:
            continue
        fill = shape.get("fill") or ""
        if not _is_renderable_solid_fill(fill):
            continue
        color = _normalize_fill(fill)
        # _is_renderable_solid_fill already rejects greys / black / white /
        # url() / "none" — but extra-guard the shape so an unexpected
        # named colour (e.g. "red") doesn't slip in and break the hex
        # parsing below.
        if not (color.startswith("#") and len(color) == 7):
            continue
        if local == "path" and _path_is_outline_frame(shape):
            # Same rationale as in apply_grayscale_density_hatching:
            # CSS borders come through as hollow frame paths and the
            # bbox covers the surrounded content (text, swatches, …).
            # Leave the path alone so it plots as its outline.
            continue
        if local == "rect":
            bbox = _rect_bbox_user_units(shape, parent_map, root)
        else:
            bbox = _path_bbox_user_units(shape, parent_map, root)
        if bbox is None:
            continue
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        if area < min_area_pt2:
            continue
        if _bbox_contains_text(bbox, text_positions):
            # Skip any shape whose AABB encloses text — hatching it
            # would paint parallel lines across the glyphs and the
            # operator reads the result as "text barred". Leaves the
            # shape as its outline instead, which on the typical
            # styled-callout / button case is what the operator
            # actually expects to see.
            continue
        buckets.setdefault(color, []).append((shape, bbox))

    if not buckets:
        return 0


    replaced = 0
    for color in sorted(buckets):
        items = buckets[color]
        darkness = 1.0 - _luminance_0_1(color)
        spacing = max_spacing_pt - darkness * (max_spacing_pt - min_spacing_pt)
        hatch_group = ET.Element(f"{{{_SVG_NS}}}g")
        hatch_group.set(_INKSCAPE_LABEL, f"color-{color}")
        hatch_group.set("stroke", color)
        hatch_group.set("fill", color)  # swatch source for layers._group_color
        hatch_group.set("stroke-width", f"{stroke_width_pt:.3f}")
        for shape, bbox in items:
            for angle_deg in (45.0, -45.0):
                for x1, y1, x2, y2 in _hatch_lines_for_bbox(
                    bbox, math.radians(angle_deg), spacing
                ):
                    path_el = ET.Element(f"{{{_SVG_NS}}}path")
                    path_el.set("d", f"M{x1:.3f} {y1:.3f}L{x2:.3f} {y2:.3f}")
                    hatch_group.append(path_el)
            parent = parent_map.get(shape)
            if parent is not None:
                parent.remove(shape)
            replaced += 1
        _insert_background_layer(root, hatch_group)
    return replaced


def rasterize_solid_color_fills(
    root: ET.Element,
    *,
    pdf_bytes: bytes,
    page_index: int,
    bitmap_options: dict[str, Any] | None = None,
    min_area_pt2: float = 50.0,
) -> tuple[int, list[str]]:
    """Replace solid-colored rect fills with bitmap-rendered strokes.

    For HTML / PDF sources, large solid-color rectangles (CSS
    background-color divs, color-bar swatches, grayscale ramps) plot as
    a flat outline by default because vpype only reads stroke geometry
    from ``<rect>``. To match the bitmap-converter behavior the
    operator gets on a PNG of the same page — where each color region
    is hatched / halftoned / dithered per the selected algorithm — we
    crop the original PDF at each rect's bbox, render it as PNG, run
    it through the bitmap converter (which applies the operator's
    algorithm choice) and substitute the result for the rect.

    Same-color rects are merged into a single ``color-{hex}`` labeled
    group so the operator's layer ↔ pen routing is unchanged from the
    vector path; only the per-layer geometry swaps flat outline →
    algorithm-rendered strokes. Pure-black and pure-white fills are
    skipped (black is text/registration ink, white is page background)
    and rects below ``min_area_pt2`` are skipped (typically border
    slivers, text underlines).

    Returns ``(count, warnings)`` like :func:`vectorize_embedded_images`.
    """
    from pen_plotter.converters.bitmap import BitmapConverter

    warnings: list[str] = []
    parent_map = {child: parent for parent in root.iter() for child in parent}
    # WeasyPrint emits ``background-color`` divs as ``<path>`` (orthogonal
    # rectangle d-strings) rather than ``<rect>``; PyMuPDF's PDF-to-SVG
    # produces a mix. Accept both — the bbox helpers below handle each.
    candidates = [
        shape
        for shape in root.iter()
        if _local(shape.tag) in {"rect", "path"}
        and _is_renderable_solid_fill(shape.get("fill") or "")
    ]
    if not candidates:
        return 0, warnings

    try:
        import pymupdf
    except ImportError:
        warnings.append("PyMuPDF unavailable — solid color fills left as-is.")
        return 0, warnings

    converter = BitmapConverter()
    produced = 0
    # Reused per color so multiple rects of the same hue land in one
    # labeled layer — keeps the layer count tractable on a CMYKRGB test
    # page (one group per ink rather than one per swatch).
    color_groups: dict[str, ET.Element] = {}

    def _shape_bbox(shape: ET.Element) -> tuple[float, float, float, float] | None:
        if _local(shape.tag) == "rect":
            return _rect_bbox_user_units(shape, parent_map, root)
        return _path_bbox_user_units(shape, parent_map, root)

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        if not 0 <= page_index < doc.page_count:
            warnings.append("Solid-fill rasterisation skipped: page index out of range.")
            return 0, warnings
        page = doc[page_index]

        for index, rect in enumerate(candidates, start=1):
            parent = parent_map.get(rect)
            if parent is None:
                continue
            bbox = _shape_bbox(rect)
            if bbox is None:
                continue
            x_min, y_min, x_max, y_max = bbox
            area = (x_max - x_min) * (y_max - y_min)
            if area < min_area_pt2:
                # Tiny rect — almost always a border sliver or text-decoration
                # line; cheaper and more readable to leave as a vector outline.
                continue
            color_key = _normalize_fill(rect.get("fill"))
            try:
                pix = page.get_pixmap(
                    clip=pymupdf.Rect(x_min, y_min, x_max, y_max), dpi=300
                )
                png_bytes = pix.tobytes("png")
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Solid-fill #{index}: page-crop render failed ({exc}).")
                continue
            try:
                result: ConversionResult = converter.convert(
                    png_bytes, options=bitmap_options
                )
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Solid-fill #{index}: vectorisation failed ({exc}).")
                continue
            groups = _inner_groups(result.svg)
            if not groups:
                # Drop the rect so the page doesn't carry an invisible
                # silhouette where the operator expected hatching.
                parent.remove(rect)
                continue
            try:
                inner_root = ET.fromstring(result.svg)
                vb = inner_root.get("viewBox", "")
                _, _, src_w, src_h = (float(v) for v in vb.split())
            except (ET.ParseError, ValueError):
                warnings.append(f"Solid-fill #{index}: bitmap result missing viewBox.")
                continue
            dst_w = x_max - x_min
            dst_h = y_max - y_min
            sx = dst_w / max(src_w, 1e-9)
            sy = dst_h / max(src_h, 1e-9)
            # Each rect's bitmap output is positioned by an outer wrapper
            # that translates+scales it back into the page. The wrappers
            # live as siblings inside the per-color ``color-{hex}`` group
            # so the operator still sees one layer per ink even when the
            # page has many same-color swatches.
            position_wrapper = ET.Element(f"{{{_SVG_NS}}}g")
            position_wrapper.set("transform", f"translate({x_min} {y_min}) scale({sx} {sy})")
            for group in groups:
                # The bitmap converter's internal per-color labels would
                # otherwise compete with our ``color-{hex}`` outer label.
                group.attrib.pop(_INKSCAPE_LABEL, None)
                position_wrapper.append(group)

            outer = color_groups.get(color_key)
            if outer is None:
                outer = ET.Element(f"{{{_SVG_NS}}}g")
                outer.set(_INKSCAPE_LABEL, f"color-{color_key}")
                outer.set("fill", color_key)  # swatch source for layers.py
                color_groups[color_key] = outer
                root.append(outer)
            outer.append(position_wrapper)

            parent.remove(rect)
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
    would plot as nothing anyway, and so are pure-white fills (PyMuPDF
    inserts ``<path fill="#ffffff">`` rectangles as the backdrop for
    CSS-styled blocks and grid patterns; on a white page they paint
    nothing the operator wants the pen to trace).
    """
    invisible = {"none", "#ffffff"}
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
            if key in invisible:
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
            # PyMuPDF emits text glyphs as ``<g transform="matrix(font_size
            # 0 0 -font_size x y)"><path d="M0..1 ..."/></g>`` — the
            # path's d-string lives in 0..1 glyph-em units and only
            # becomes the right size + position once the wrapper's
            # transform is applied. Detaching the leaf without
            # preserving that ancestor chain collapses every glyph to a
            # 1-point dot at the origin (so text "vanishes" from the
            # editor preview and from the gcode). Walk every ancestor
            # transform between ``parent`` and ``root`` and replay them
            # as a single composed wrapper around the moved leaf.
            ancestor_transforms = _ancestor_transforms_to_root(parent, parent_map, root)
            parent.remove(leaf)
            if ancestor_transforms:
                transform_wrap = ET.Element(f"{{{_SVG_NS}}}g")
                transform_wrap.set("transform", " ".join(ancestor_transforms))
                transform_wrap.append(leaf)
                wrapper.append(transform_wrap)
            else:
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

    # Z-order: insert the new (mostly text-bearing) groups AFTER any
    # background-style labelled layers — ``color-#rrggbb`` and
    # ``grayscale`` come from the density-hatching passes which
    # represent CSS-backgrounded boxes. In SVG, later siblings render
    # on top, so the hatching for a coloured background must sit BELOW
    # the text glyphs that ride over it (otherwise the user sees text
    # "struck through" by hatch lines). Other labelled layers
    # (``image-N``, Hershey ``text``, ``pattern-N``) keep their
    # existing position relative to the text by being skipped over too.
    insert_at = len(root)
    background_labels = {"grayscale"}
    for i, child in enumerate(root):
        if _local(child.tag) != "g":
            continue
        child_label = child.get(_INKSCAPE_LABEL)
        if child_label is None:
            continue
        if child_label in background_labels or child_label.startswith("color-"):
            # Background-style: text goes after it.
            insert_at = i + 1
        else:
            # Non-background labelled layer (image-N, hershey text, …)
            # — keep the prior "insert before" semantics so e.g. a
            # Hershey re-render still ends up adjacent to its peer.
            insert_at = i
            break
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
        # Greyscale swatches go FIRST: fold every R==G==B-filled shape
        # into a single density-modulated black layer. This runs before
        # ``rasterize_solid_color_fills`` (which deliberately skips
        # greys) so a CMYKRGB + 11-bar grey-ramp test page produces one
        # ``grayscale`` layer instead of eleven ``color-#nnnnnn``
        # layers — the operator wants one pen for the whole ramp, with
        # hatching density doing the work of luminance.
        apply_grayscale_density_hatching(root)
        # Then the colored CSS divs / swatches. Two code paths:
        #
        # * No operator-supplied bitmap options → density hatching per
        #   colour (mirroring the grayscale path above). This produces
        #   a plotted-looking fill out of the box: a red box becomes a
        #   red crosshatch group, a blue box becomes a blue crosshatch
        #   group, etc. Without this the BitmapConverter's default
        #   ``direct`` algorithm only traces the rectangle's perimeter
        #   via potrace, so the operator gets a bare outline instead of
        #   a fill — the user's complaint on the print-test HTML.
        # * Operator-supplied bitmap options → defer to
        #   ``rasterize_solid_color_fills`` which crops the page and
        #   runs each region through the chosen algorithm (crosshatch /
        #   halftone / stippling / …). This keeps the existing path for
        #   anyone explicitly picking a style.
        if bitmap_options:
            _, solid_warnings = rasterize_solid_color_fills(
                root,
                pdf_bytes=pdf_bytes,
                page_index=page_index,
                bitmap_options=bitmap_options,
            )
            pattern_warnings.extend(solid_warnings)
        else:
            apply_color_density_hatching(root)
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
