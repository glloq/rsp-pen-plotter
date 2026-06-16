// Physical pen-width rendering helpers.
//
// Each available colour carries a ``stroke_width_mm`` (the marker tip
// width). The conversion algorithms emit their geometry in the source
// image's pixel space with a fixed ``stroke-width`` on each coloured
// ``<g>`` group, so the on-screen thickness would otherwise depend on
// the image resolution and placement scale — not the real pen.
//
// These helpers rewrite the rendered ``stroke-width`` so every coloured
// group displays at its assigned pen's *physical* width. We match groups
// by their ``stroke`` colour (robust to sanitizers stripping the
// ``inkscape:label``) and convert mm → the SVG's user-unit space via the
// caller-supplied ``mmPerUnit`` (placement mm ÷ viewBox units). Because
// the conversion is applied live at display time, it stays correct when
// the operator resizes a placement.

const DEFAULT_STROKE_WIDTH_MM = 0.5

/**
 * A physical mark a pen lays down: a line/stroke ``'width'`` (floors at
 * the tip diameter) or a dot ``'radius'`` (floors at half the diameter).
 */
export type PenMarkKind = 'radius' | 'width'

/**
 * The mm floor a ``kind`` of mark can't go below for a pen whose tip is
 * ``minPenWidthMm`` across — you can't draw a line thinner than the tip,
 * nor a dot whose radius is under half the tip. Returns ``null`` when no
 * positive pen width is known (caller keeps its own bound).
 */
export function penMarkFloorMm(kind: PenMarkKind, minPenWidthMm?: number | null): number | null {
  if (typeof minPenWidthMm !== 'number' || !(minPenWidthMm > 0)) return null
  return kind === 'radius' ? minPenWidthMm / 2 : minPenWidthMm
}

/**
 * Algorithm-schema option keys (``AlgoOption.key``) that name a physical
 * pen mark, so the schema-driven form (``AlgoParamsForm``) can raise
 * their lower bound to the pen in use — the same floor the master-style
 * ``dot_radius`` / ``stroke_width`` knobs get. ``stroke_width`` is listed
 * for robustness even though edges/centerline currently inject it from
 * the pen slot rather than exposing a schema knob.
 */
export const ALGO_PEN_FLOOR_KEYS: Readonly<Record<string, PenMarkKind>> = {
  dot_radius_mm: 'radius',
  stroke_width: 'width',
}

/**
 * Parse a stroke-width form field into a positive number of mm, or
 * ``null`` when blank / invalid.
 *
 * ``v-model.number`` *usually* hands the component a number, but a real
 * browser can leave a raw string in the bound ref — e.g. a locale where
 * the numeric keypad emits ``0,8`` with a comma decimal separator. A
 * strict ``Number.isFinite(value)`` guard returns ``false`` for *any*
 * string (it doesn't coerce), so the width would be silently dropped
 * from the PATCH: the colour saves but its diameter never changes. We
 * normalise the comma → dot and coerce here so the edit is robust to
 * both the value's type and the operator's locale.
 */
export function parsePenWidthMm(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) && value > 0 ? value : null
  }
  // Extract the first decimal number from the raw text so the field is
  // robust to what operators naturally type: a comma separator ("0,8"),
  // leading/trailing spaces, and — crucially — a trailing unit ("0.8mm",
  // "0,8 mm") since the UI shows "mm" right next to the input. Without
  // this, "0.8mm" parsed to null and the save silently fell back to the
  // 0.5 default, so the diameter appeared stuck.
  const match = String(value)
    .replace(',', '.')
    .match(/-?\d*\.?\d+/)
  if (!match) return null
  const n = Number(match[0])
  return Number.isFinite(n) && n > 0 ? n : null
}

/** Canonicalise a hex string to lowercase ``#rrggbb`` (expands ``#rgb``). */
export function canonicalHex(value: string): string {
  const trimmed = value.trim().replace(/^#/, '').toLowerCase()
  if (/^[0-9a-f]{3}$/.test(trimmed)) {
    return `#${trimmed
      .split('')
      .map((c) => c + c)
      .join('')}`
  }
  if (/^[0-9a-f]{6}$/.test(trimmed)) return `#${trimmed}`
  return value.trim().toLowerCase()
}

/** Build a canonical-hex → stroke width (mm) lookup from the inventory. */
export function strokeWidthMmByHex(
  colors: ReadonlyArray<{ hex: string; stroke_width_mm: number }>,
): Map<string, number> {
  const map = new Map<string, number>()
  for (const c of colors) {
    if (c.stroke_width_mm > 0) map.set(canonicalHex(c.hex), c.stroke_width_mm)
  }
  return map
}

/** Parse the ``mm per viewBox unit`` scale for a placement, or null. */
export function mmPerViewBoxUnit(svg: string, widthMm: number, heightMm: number): number | null {
  const match = svg.match(/viewBox\s*=\s*"([^"]+)"/)
  if (!match) return null
  const parts = match[1]!
    .trim()
    .split(/[\s,]+/)
    .map(Number)
  if (parts.length !== 4 || !parts.every(Number.isFinite)) return null
  const vbW = parts[2]!
  const vbH = parts[3]!
  if (vbW <= 0 || vbH <= 0 || widthMm <= 0 || heightMm <= 0) return null
  // Geometric mean keeps a single uniform stroke even when the placement
  // aspect ratio differs slightly from the source (stroke-width is scalar).
  return Math.sqrt((widthMm / vbW) * (heightMm / vbH))
}

// Absolute CSS length units → millimetres. ``px`` and unitless values are
// deliberately excluded: they carry no reliable physical scale (a 24×24
// icon must not be read as a 24 mm page), so a length in those units
// yields ``null`` and the caller falls back to fitting the content.
const ABS_LENGTH_TO_MM: Readonly<Record<string, number>> = {
  mm: 1,
  cm: 10,
  in: 25.4,
  pt: 25.4 / 72,
  pc: 25.4 / 6,
}

/** Parse a CSS length carrying an *absolute* unit into mm, or null. */
function absoluteLengthMm(raw: string | null): number | null {
  if (!raw) return null
  const m = raw.trim().match(/^\+?(\d*\.?\d+)\s*(mm|cm|in|pt|pc)$/i)
  if (!m) return null
  const value = Number(m[1])
  const factor = ABS_LENGTH_TO_MM[m[2]!.toLowerCase()]
  if (!(value > 0) || factor === undefined) return null
  return value * factor
}

/** Read a quoted attribute off an opening tag string, or null. The
 *  leading whitespace requirement keeps ``width`` from matching the
 *  ``-width`` tail of ``stroke-width``. */
function tagAttr(tag: string, name: string): string | null {
  const m = tag.match(new RegExp(`\\s${name}\\s*=\\s*"([^"]*)"|\\s${name}\\s*=\\s*'([^']*)'`, 'i'))
  if (!m) return null
  return m[1] ?? m[2] ?? null
}

/**
 * Physical page size (mm) a raw SVG was authored for, read from the root
 * ``<svg width=… height=…>`` when *both* carry an absolute unit
 * (mm / cm / in / pt / pc). Inkscape and Illustrator stamp these on every
 * "A4" / "A5" export, letting the caller size the on-sheet placement to
 * the real page instead of rescaling the artwork to fill the workspace.
 *
 * Returns ``null`` when a dimension is missing, a percentage, or in
 * ``px`` / unitless user units — none of which pin a real-world size — so
 * the caller keeps its fit-to-workspace fallback for those.
 */
export function svgIntrinsicPageSizeMm(
  svg: string,
): { width_mm: number; height_mm: number } | null {
  const root = svg.match(/<svg\b[^>]*>/i)?.[0]
  if (!root) return null
  const width_mm = absoluteLengthMm(tagAttr(root, 'width'))
  const height_mm = absoluteLengthMm(tagAttr(root, 'height'))
  if (width_mm === null || height_mm === null) return null
  return { width_mm, height_mm }
}

/**
 * Rewrite the root ``<svg>``'s ``viewBox`` to the given bounding box (in
 * SVG user units) so the displayed area is exactly the inked content
 * instead of the full page. Without this, text / PDF / HTML SVGs render
 * with their original page-sized viewBox: the content's margin offset
 * shows up as empty space at the top-left of the placement and any
 * content past the placement's footprint gets clipped on the bottom-right.
 *
 * The function leaves ``width`` / ``height`` attributes untouched —
 * downstream callers force them via CSS to fit the placement. Returns
 * the input unchanged when the bbox is degenerate or the SVG has no
 * recognisable root tag.
 */
export function cropSvgViewBoxToBbox(
  svg: string,
  bbox: { x_min: number; y_min: number; x_max: number; y_max: number },
): string {
  const w = bbox.x_max - bbox.x_min
  const h = bbox.y_max - bbox.y_min
  if (!(w > 0) || !(h > 0)) return svg
  if (!Number.isFinite(bbox.x_min) || !Number.isFinite(bbox.y_min)) return svg
  const newViewBox = `${bbox.x_min} ${bbox.y_min} ${w} ${h}`
  if (/viewBox\s*=\s*"[^"]*"/.test(svg)) {
    return svg.replace(/viewBox\s*=\s*"[^"]*"/, `viewBox="${newViewBox}"`)
  }
  return svg.replace(/<svg\b/i, `<svg viewBox="${newViewBox}"`)
}

/**
 * Rewrite the ``stroke-width`` of every coloured group so it renders at
 * the assigned pen's physical width. Only colours present in
 * ``hexToMm`` (i.e. declared pens in the inventory) are touched; any
 * other stroke is left at whatever the algorithm emitted. Returns the
 * input unchanged when it can't be parsed or nothing matched.
 */
export function applyPhysicalStrokeWidth(
  svg: string,
  hexToMm: Map<string, number>,
  mmPerUnit: number,
): string {
  if (!svg || !(mmPerUnit > 0) || hexToMm.size === 0) return svg
  let doc: Document
  try {
    doc = new DOMParser().parseFromString(svg, 'image/svg+xml')
  } catch {
    return svg
  }
  if (doc.querySelector('parsererror') || !doc.documentElement) return svg
  let touched = false
  for (const el of Array.from(doc.querySelectorAll('[stroke]'))) {
    const stroke = el.getAttribute('stroke')
    if (!stroke || stroke === 'none') continue
    const mm = hexToMm.get(canonicalHex(stroke))
    if (mm === undefined) continue
    const units = mm / mmPerUnit
    if (units > 0 && Number.isFinite(units)) {
      el.setAttribute('stroke-width', units.toFixed(4))
      touched = true
    }
  }
  if (!touched) return svg
  return new XMLSerializer().serializeToString(doc.documentElement)
}

/**
 * Build the per-layer pen width map (viewBox units) for ``/rerender``,
 * keyed by layer id. Each layer's width comes from its assigned colour
 * (falling back to its source colour) looked up in the inventory, then
 * converted mm → viewBox units via ``mmPerUnit``. Layers whose colour
 * isn't a declared pen are omitted so the backend keeps its default.
 */
export function layerStrokeWidthsPx(
  layers: ReadonlyArray<{
    layer_id: string
    source_color: string
    assigned_color_hex: string | null
  }>,
  hexToMm: Map<string, number>,
  mmPerUnit: number,
): Record<string, number> {
  const out: Record<string, number> = {}
  if (!(mmPerUnit > 0) || hexToMm.size === 0) return out
  for (const layer of layers) {
    const hex = canonicalHex(layer.assigned_color_hex ?? layer.source_color)
    const mm = hexToMm.get(hex)
    if (mm === undefined) continue
    const units = mm / mmPerUnit
    if (units > 0 && Number.isFinite(units)) out[layer.layer_id] = units
  }
  return out
}

export { DEFAULT_STROKE_WIDTH_MM }
