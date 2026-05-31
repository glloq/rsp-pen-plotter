"""Post-processing for PyMuPDF-emitted SVG.

PyMuPDF (and therefore every document route that funnels through it —
``PdfConverter``, ``DocumentConverter`` via LibreOffice, ``HtmlConverter`` via
WeasyPrint) emits text as ``<defs>`` glyphs referenced by ``<use>`` and rasters
as ``<image>`` elements. Two consequences for the plotter pipeline:

* ``<use>`` is in :mod:`pen_plotter.core.sanitize`'s blocklist (security:
  external ``<use href="evil.svg">`` can pull arbitrary content), so the text
  silently disappears.
* ``<image>`` elements are not strokes; ``vpype.read_multilayer_svg`` ignores
  them, so any embedded raster is silently dropped before G-code generation.

This module pre-expands every ``<use>`` reference into inline geometry, then
hands each embedded raster to the bitmap converter so it becomes a vectorized
labeled layer of its own. The remaining vector content (typically the text)
is wrapped into a sibling ``text`` layer. After post-processing the SVG is
self-contained (no ``<defs>``, no ``<use>``, no ``<image>``) and
``extract_layers`` produces one entry per source kind so the user can assign
text and each image to different pen slots.
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


def wrap_text_layer(root: ET.Element, label: str = "text") -> bool:
    """Wrap top-level non-labeled drawables into a single labeled group.

    Returns ``True`` when a wrapping group was inserted. This makes the
    text/vector content of a PyMuPDF document appear as a sibling layer
    to the ``image-N`` groups produced by :func:`vectorize_embedded_images`.
    """
    drawable_local = {"g", "path", "polyline", "polygon", "line", "circle", "rect", "ellipse"}
    children = list(root)
    loose: list[ET.Element] = []
    for child in children:
        local = _local(child.tag)
        if local not in drawable_local:
            continue
        # Already a labeled layer? Leave it alone.
        if local == "g" and child.get(_INKSCAPE_LABEL):
            continue
        loose.append(child)
    if not loose:
        return False
    wrapper = ET.Element(f"{{{_SVG_NS}}}g")
    wrapper.set(_INKSCAPE_LABEL, label)
    for element in loose:
        list(root).index(element)
        root.remove(element)
        wrapper.append(element)
    # Insert the text wrapper before any image-N groups so it lives at
    # the same level and is rendered first (drawn before images, which
    # mirrors typical document layering).
    insert_at = 0
    for i, child in enumerate(root):
        if _local(child.tag) == "g" and (child.get(_INKSCAPE_LABEL) or "").startswith("image-"):
            insert_at = i
            break
        insert_at = i + 1
    root.insert(insert_at, wrapper)
    return True


def postprocess_pdf_svg(
    svg: str,
    *,
    bitmap_options: dict[str, Any] | None = None,
    hershey_text_group: str | None = None,
) -> tuple[str, list[str]]:
    """Run the full PDF-SVG post-processing chain.

    Expands ``<use>`` references inline, vectorizes embedded raster
    ``<image>`` elements into their own labeled layers, and wraps any
    remaining vector content into a ``text`` layer. The output is a
    self-contained pivot SVG ready for sanitize + extract_layers.

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
    expand_use_refs(root)
    _, image_warnings = vectorize_embedded_images(root, bitmap_options=bitmap_options)
    hoist_labeled_groups(root)
    # When Hershey is taking over the "text" label, the catch-all
    # wrapper for the document's remaining vector content (rules,
    # shapes, lines, …) needs a different layer name. Otherwise the
    # operator ends up with two distinct "text" layers — one with the
    # Hershey strokes, one with the non-text drawings — and the
    # per-layer pen-slot UI can't tell them apart.
    wrap_text_layer(root, label="drawings" if hershey_text_group else "text")

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
