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
  const n = typeof value === 'number' ? value : Number(String(value).replace(',', '.').trim())
  return Number.isFinite(n) && n > 0 ? n : null
}

/** Canonicalise a hex string to lowercase ``#rrggbb`` (expands ``#rgb``). */
export function canonicalHex(value: string): string {
  const trimmed = value.trim().replace(/^#/, '').toLowerCase()
  if (/^[0-9a-f]{3}$/.test(trimmed)) {
    return `#${trimmed.split('').map((c) => c + c).join('')}`
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
  const parts = match[1]!.trim().split(/[\s,]+/).map(Number)
  if (parts.length !== 4 || !parts.every(Number.isFinite)) return null
  const vbW = parts[2]!
  const vbH = parts[3]!
  if (vbW <= 0 || vbH <= 0 || widthMm <= 0 || heightMm <= 0) return null
  // Geometric mean keeps a single uniform stroke even when the placement
  // aspect ratio differs slightly from the source (stroke-width is scalar).
  return Math.sqrt((widthMm / vbW) * (heightMm / vbH))
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
