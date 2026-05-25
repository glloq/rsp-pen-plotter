// Compose multiple placement snapshots into a single workspace-scale SVG
// the backend can extract layers from. Each placement gets wrapped in a
// ``<g transform="translate(...) scale(...)">`` and its ``inkscape:label``
// attributes are prefixed with the placement id so the same layer
// (e.g. ``color-ff0000``) appearing in two different placements does not
// collide — the backend treats them as independent layers, each with its
// own pen / speed / pause config.
//
// We parse each placement's SVG with ``DOMParser`` (read-only) and
// generate the output as a string so the result is predictable in both
// real browsers and test environments without depending on the quirks
// of ``document.implementation.createDocument``.

import type { BoundingBox, LayerInfo, MachineProfile } from '../api/client'

const SVG_NS = 'http://www.w3.org/2000/svg'
const INKSCAPE_NS = 'http://www.inkscape.org/namespaces/inkscape'

export interface PlacementSnapshot {
  id: string
  svg: string
  layers: LayerInfo[]
  source_bbox: BoundingBox
  visibility: Record<string, boolean>
  x_mm: number
  y_mm: number
  width_mm: number
  height_mm: number
  // Optional rigid-body transforms applied to the placement content
  // before it lands at (x_mm, y_mm). Default 0 / false for legacy
  // snapshots that pre-date the editing tools.
  rotation?: number
  flip_h?: boolean
  flip_v?: boolean
}

export interface CompositeResult {
  svg: string
  layers: LayerInfo[]
}

export function compositeLayerId(placementId: string, layerId: string): string {
  return `${placementId}__${layerId}`
}

/** Build a composite SVG covering the whole machine workspace. */
export function buildComposite(
  placements: PlacementSnapshot[],
  profile: MachineProfile,
): CompositeResult {
  const ws = profile.workspace
  const wsW = ws.x_max - ws.x_min
  const wsH = ws.y_max - ws.y_min
  if (!Number.isFinite(wsW) || !Number.isFinite(wsH) || wsW <= 0 || wsH <= 0) {
    return { svg: openSvg(ws.x_min, ws.y_min, 1, 1) + closeSvg(), layers: [] }
  }

  const compositeLayers: LayerInfo[] = []
  const groupChunks: string[] = []
  let order = 0
  const parser = new DOMParser()

  for (const p of placements) {
    const inner = extractPlacementChunk(parser, p)
    if (!inner) continue
    groupChunks.push(inner.svgChunk)
    for (const layer of p.layers) {
      if (p.visibility[layer.layer_id] === false) continue
      compositeLayers.push({
        ...layer,
        layer_id: compositeLayerId(p.id, layer.layer_id),
        draw_order: order++,
        total_length_mm: layer.total_length_mm * inner.scaleAvg,
        bbox: transformBbox(layer.bbox, inner),
      })
    }
  }

  return {
    svg: openSvg(ws.x_min, ws.y_min, wsW, wsH) + groupChunks.join('') + closeSvg(),
    layers: compositeLayers,
  }
}

interface PlacementChunk {
  svgChunk: string
  // 2×3 affine matrix [a b c d e f] mapping a point (vx, vy) in the
  // placement's intrinsic viewBox to workspace mm:
  //   x_mm = a*vx + c*vy + e
  //   y_mm = b*vx + d*vy + f
  // The matrix bakes scale + rotation + flip + translate so the gcode
  // backend sees the same geometry as the on-screen preview.
  a: number
  b: number
  c: number
  d: number
  e: number
  f: number
  scaleAvg: number
}

function transformPoint(chunk: PlacementChunk, x: number, y: number): { x: number; y: number } {
  return {
    x: chunk.a * x + chunk.c * y + chunk.e,
    y: chunk.b * x + chunk.d * y + chunk.f,
  }
}

function transformBbox(box: BoundingBox, chunk: PlacementChunk): BoundingBox {
  // Rotation can swap the bbox extremes, so map all four corners and
  // take the min/max — this stays correct for any combination of
  // rotation / mirror / scale.
  const corners = [
    transformPoint(chunk, box.x_min, box.y_min),
    transformPoint(chunk, box.x_min, box.y_max),
    transformPoint(chunk, box.x_max, box.y_min),
    transformPoint(chunk, box.x_max, box.y_max),
  ]
  let x_min = Infinity
  let y_min = Infinity
  let x_max = -Infinity
  let y_max = -Infinity
  for (const c of corners) {
    if (c.x < x_min) x_min = c.x
    if (c.x > x_max) x_max = c.x
    if (c.y < y_min) y_min = c.y
    if (c.y > y_max) y_max = c.y
  }
  return { x_min, y_min, x_max, y_max }
}

function extractPlacementChunk(parser: DOMParser, p: PlacementSnapshot): PlacementChunk | null {
  const doc = parser.parseFromString(p.svg, 'image/svg+xml')
  if (doc.querySelector('parsererror')) return null
  const root = doc.documentElement
  if (!root) return null

  // Resolve the placement's intrinsic viewBox. If it's absent we fall
  // back to the layers' union bbox (passed in as ``source_bbox``).
  const vbAttr = root.getAttribute('viewBox') ?? ''
  const vbParts = vbAttr.split(/\s+/).map(Number)
  let vbX = 0
  let vbY = 0
  let vbW = p.source_bbox.x_max - p.source_bbox.x_min || 1
  let vbH = p.source_bbox.y_max - p.source_bbox.y_min || 1
  if (vbParts.length === 4 && vbParts.every(Number.isFinite)) {
    vbX = vbParts[0]!
    vbY = vbParts[1]!
    vbW = vbParts[2]!
    vbH = vbParts[3]!
  }
  if (vbW <= 0 || vbH <= 0) return null

  const rotation = ((((p.rotation ?? 0) % 360) + 360) % 360) as 0 | 90 | 180 | 270
  const flipX = p.flip_h ? -1 : 1
  const flipY = p.flip_v ? -1 : 1
  // After a quarter-turn the viewBox's vbH dimension lies along the
  // workspace X axis (and vbW along Y) — see ``rotatePlacement`` in the
  // job store, which swaps width_mm/height_mm on rotate. The scale
  // factors below are applied AFTER the rotation (post-multiplication
  // in the transform chain), so they're keyed to the post-rotation
  // dimension that lands on each axis.
  const rotated = rotation === 90 || rotation === 270
  const sx = rotated ? p.width_mm / vbH : p.width_mm / vbW
  const sy = rotated ? p.height_mm / vbW : p.height_mm / vbH

  // Build a 2×3 affine matrix that maps the placement viewBox into
  // workspace mm, applying the user's rigid-body edits. Conceptually:
  //
  //   M = T(x_mm, y_mm)
  //       · T(width/2, height/2)              // bbox centre → origin
  //       · Scale(sx, sy)                     // viewBox → bbox extent
  //       · Rot(theta)
  //       · Scale(flipX, flipY)
  //       · T(-vbW/2 - vbX, -vbH/2 - vbY)     // viewBox centre → origin
  //
  // We compose it analytically so the resulting transform stays a
  // single ``matrix(...)`` SVG attribute the backend can parse.
  const theta = (rotation * Math.PI) / 180
  const cos = Math.round(Math.cos(theta))
  const sin = Math.round(Math.sin(theta))
  // Rotation+flip mapping in viewBox-centred space: combined linear part
  // is Rot(theta) · diag(flipX, flipY).
  const r11 = cos * flipX
  const r12 = -sin * flipY
  const r21 = sin * flipX
  const r22 = cos * flipY
  // Linear part of M (apply scale after the rotation+flip).
  const a = sx * r11
  const b = sy * r21
  const c = sx * r12
  const d = sy * r22
  // Translation: image of the viewBox centre under the linear part, then
  // shifted to the bbox centre in workspace coords.
  const cxVb = vbX + vbW / 2
  const cyVb = vbY + vbH / 2
  const cxBox = p.x_mm + p.width_mm / 2
  const cyBox = p.y_mm + p.height_mm / 2
  const e = cxBox - (a * cxVb + c * cyVb)
  const f = cyBox - (b * cxVb + d * cyVb)

  // Emit a simpler ``translate(...) scale(...)`` when there's no
  // rotation or flip, both so the SVG stays human-readable and so the
  // existing test suite (which asserts that exact substring) keeps
  // matching. Otherwise fall through to a full ``matrix(...)``.
  const isIdentityRigidBody = rotation === 0 && !p.flip_h && !p.flip_v
  const transformAttr = isIdentityRigidBody
    ? `translate(${e} ${f}) scale(${sx} ${sy})`
    : `matrix(${a} ${b} ${c} ${d} ${e} ${f})`

  // Each labeled inner group becomes a TOP-LEVEL ``<g>`` in the composite,
  // carrying the placement transform directly on it. The backend's
  // ``labeled_group_fragments`` only sees groups that are direct children
  // of ``<svg>``, so nesting labeled groups inside an outer transform
  // wrapper hides them from the layer-extraction pipeline — per-layer
  // pen / speed / pause overrides keyed by the composite layer id would
  // never match anything and every layer would silently fall back to the
  // profile defaults. Hoisting them keeps the SVG semantics: each labeled
  // group is a layer, transformed into workspace coordinates.
  const chunks: string[] = []
  const unlabeled: string[] = []
  for (const child of Array.from(root.children)) {
    if (!(child instanceof Element)) continue
    if (child.tagName.toLowerCase() === 'g') {
      const label =
        child.getAttribute('inkscape:label') ?? child.getAttributeNS(INKSCAPE_NS, 'label') ?? null
      if (label) {
        if (p.visibility[label] === false) continue
        chunks.push(
          serializeLabeledGroup(child, compositeLayerId(p.id, label), transformAttr, p.id),
        )
        continue
      }
    }
    unlabeled.push(serializeElement(child))
  }
  // Sources that have no labeled groups (single-colour uploads) are
  // surfaced as a single ``${placement}__layer-1`` layer so per-layer
  // overrides keyed on that id still apply. Honour the visibility flag
  // for ``layer-1`` if the operator hid it.
  if (unlabeled.length && p.visibility['layer-1'] !== false) {
    const synthLabel = compositeLayerId(p.id, 'layer-1')
    chunks.push(
      `<g inkscape:label="${escapeAttr(synthLabel)}" ` +
        `data-placement-id="${escapeAttr(p.id)}" ` +
        `transform="${transformAttr}">` +
        unlabeled.join('') +
        '</g>',
    )
  }

  return {
    svgChunk: chunks.join(''),
    a,
    b,
    c,
    d,
    e,
    f,
    scaleAvg: Math.sqrt(Math.abs(sx * sy)) || 1,
  }
}

function serializeLabeledGroup(
  el: Element,
  newLabel: string,
  outerTransform: string,
  placementId: string,
): string {
  // Re-emit the labeled group with the composite layer id, the placement
  // transform applied as the outermost transform, and the original
  // attributes preserved. If the source already had a ``transform``, we
  // prepend the placement transform: in SVG, transforms are applied
  // right-to-left, so listing the placement transform first means it
  // wraps the inner one — equivalent to ``M_outer · M_inner``.
  let existingTransform: string | null = null
  const attrs: string[] = []
  for (const attr of Array.from(el.attributes)) {
    if (attr.name === 'inkscape:label') continue
    if (attr.localName === 'label' && attr.namespaceURI === INKSCAPE_NS) continue
    if (attr.name === 'transform') {
      existingTransform = attr.value
      continue
    }
    if (attr.name === 'data-placement-id') continue
    attrs.push(`${attr.name}="${escapeAttr(attr.value)}"`)
  }
  attrs.push(`inkscape:label="${escapeAttr(newLabel)}"`)
  attrs.push(`data-placement-id="${escapeAttr(placementId)}"`)
  const composed = existingTransform ? `${outerTransform} ${existingTransform}` : outerTransform
  attrs.push(`transform="${escapeAttr(composed)}"`)
  const inner = Array.from(el.childNodes)
    .map((node) => serializeNode(node))
    .join('')
  return `<g ${attrs.join(' ')}>${inner}</g>`
}

function serializeElement(el: Element): string {
  // Use XMLSerializer when available (browsers + happy-dom), else fall
  // back to outerHTML (which uses HTML serialization, fine for shapes).
  try {
    return new XMLSerializer().serializeToString(el)
  } catch {
    return el.outerHTML
  }
}

function serializeNode(node: Node): string {
  if (node.nodeType === Node.ELEMENT_NODE) return serializeElement(node as Element)
  if (node.nodeType === Node.TEXT_NODE) return escapeText(node.nodeValue ?? '')
  return ''
}

function escapeAttr(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function escapeText(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function openSvg(x: number, y: number, w: number, h: number): string {
  return (
    `<svg xmlns="${SVG_NS}" xmlns:inkscape="${INKSCAPE_NS}" ` +
    `viewBox="${x} ${y} ${w} ${h}" width="${w}mm" height="${h}mm">`
  )
}

function closeSvg(): string {
  return '</svg>'
}
