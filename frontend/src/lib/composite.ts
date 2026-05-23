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
        bbox: {
          x_min: inner.tx + layer.bbox.x_min * inner.sx,
          y_min: inner.ty + layer.bbox.y_min * inner.sy,
          x_max: inner.tx + layer.bbox.x_max * inner.sx,
          y_max: inner.ty + layer.bbox.y_max * inner.sy,
        },
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
  sx: number
  sy: number
  tx: number
  ty: number
  scaleAvg: number
}

function extractPlacementChunk(
  parser: DOMParser,
  p: PlacementSnapshot,
): PlacementChunk | null {
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

  const sx = p.width_mm / vbW
  const sy = p.height_mm / vbH
  // The placement is positioned in workspace-relative mm. We bake the
  // workspace origin into the transform so the composite SVG's viewBox
  // can stay at the machine's (x_min, y_min).
  const tx = p.x_mm - vbX * sx
  const ty = p.y_mm - vbY * sy

  // Serialize each top-level child (rewrite labels on group elements).
  const parts: string[] = []
  for (const child of Array.from(root.children)) {
    if (!(child instanceof Element)) continue
    if (child.tagName.toLowerCase() === 'g') {
      const label
        = child.getAttribute('inkscape:label')
        ?? child.getAttributeNS(INKSCAPE_NS, 'label')
        ?? null
      if (label && p.visibility[label] === false) continue
      parts.push(serializeGroup(child, label ? compositeLayerId(p.id, label) : null))
    } else {
      parts.push(serializeElement(child))
    }
  }

  const wrapper
    = `<g data-placement-id="${escapeAttr(p.id)}" transform="translate(${tx} ${ty}) scale(${sx} ${sy})">`
    + parts.join('')
    + '</g>'
  return {
    svgChunk: wrapper,
    sx,
    sy,
    tx,
    ty,
    scaleAvg: Math.sqrt(Math.abs(sx * sy)) || 1,
  }
}

function serializeGroup(el: Element, newLabel: string | null): string {
  if (newLabel === null) return serializeElement(el)
  // Reserialize the group with the rewritten label. We strip any
  // existing inkscape:label / inkscape:label-ns attributes so the
  // output has exactly one of them with the prefixed value.
  const attrs: string[] = []
  for (const attr of Array.from(el.attributes)) {
    if (attr.name === 'inkscape:label') continue
    if (attr.localName === 'label' && attr.namespaceURI === INKSCAPE_NS) continue
    attrs.push(`${attr.name}="${escapeAttr(attr.value)}"`)
  }
  attrs.push(`inkscape:label="${escapeAttr(newLabel)}"`)
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
    `<svg xmlns="${SVG_NS}" xmlns:inkscape="${INKSCAPE_NS}" `
    + `viewBox="${x} ${y} ${w} ${h}" width="${w}mm" height="${h}mm">`
  )
}

function closeSvg(): string {
  return '</svg>'
}
