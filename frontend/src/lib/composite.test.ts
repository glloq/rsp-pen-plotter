// @vitest-environment happy-dom

import { describe, expect, it } from 'vitest'
import type { LayerInfo, MachineProfile } from '../api/client'
import { buildComposite, compositeLayerId, type PlacementSnapshot } from './composite'

function profile(overrides: Partial<MachineProfile> = {}): MachineProfile {
  return {
    name: 'Test',
    units: 'mm',
    workspace: { x_min: 0, y_min: 0, x_max: 420, y_max: 297 },
    origin: 'top_left',
    gcode_dialect: 'grbl',
    pen_up_command: '',
    pen_down_command: '',
    tool_change_method: 'manual_pause',
    tool_change_command: '',
    drawing_speed_mm_s: 60,
    travel_speed_mm_s: 120,
    acceleration_mm_s2: 1000,
    pen_slot_count: 1,
    supports_arcs: false,
    arc_tolerance_mm: 0.1,
    ebb: null,
    pens: null,
    ...overrides,
  }
}

function layer(layer_id: string): LayerInfo {
  return {
    layer_id,
    source_color: '#000000',
    target_pen_slot: null,
    draw_order: 0,
    total_length_mm: 100,
    path_count: 1,
    bbox: { x_min: 0, y_min: 0, x_max: 100, y_max: 100 },
    optimize: true,
    simplify_tolerance_mm: 0,
    drawing_speed_mm_s: null,
    color_label: null,
    pause_before: 'auto',
  }
}

function snapshot(id: string, x: number, y: number, w = 100, h = 100): PlacementSnapshot {
  const svg
    = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
    + 'viewBox="0 0 100 100">'
    + '<g inkscape:label="color-ff0000"><rect width="50" height="50" /></g>'
    + '<g inkscape:label="color-00ff00"><rect width="20" height="20" /></g>'
    + '</svg>'
  return {
    id,
    svg,
    layers: [layer('color-ff0000'), layer('color-00ff00')],
    source_bbox: { x_min: 0, y_min: 0, x_max: 100, y_max: 100 },
    visibility: { 'color-ff0000': true, 'color-00ff00': true },
    x_mm: x,
    y_mm: y,
    width_mm: w,
    height_mm: h,
  }
}

describe('compositeLayerId', () => {
  it('joins placement and layer ids with a separator', () => {
    expect(compositeLayerId('p1', 'color-ff0000')).toBe('p1__color-ff0000')
  })
})

describe('buildComposite', () => {
  it('returns a workspace-sized SVG with no placements', () => {
    const result = buildComposite([], profile())
    expect(result.svg).toContain('viewBox="0 0 420 297"')
    expect(result.layers).toEqual([])
  })

  it('wraps a single placement in a translate + scale group', () => {
    const result = buildComposite([snapshot('p1', 10, 20, 50, 50)], profile())
    expect(result.svg).toContain('viewBox="0 0 420 297"')
    // 50 mm wide drawing over 100 user units = scale 0.5; x=10 → tx=10
    expect(result.svg).toContain('translate(10 20) scale(0.5 0.5)')
    expect(result.layers).toHaveLength(2)
    expect(result.layers[0]!.layer_id).toBe('p1__color-ff0000')
    expect(result.layers[1]!.layer_id).toBe('p1__color-00ff00')
  })

  it('keeps layer ids unique across placements', () => {
    const result = buildComposite(
      [snapshot('p1', 0, 0), snapshot('p2', 200, 0)],
      profile(),
    )
    const ids = result.layers.map((l) => l.layer_id)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids).toContain('p1__color-ff0000')
    expect(ids).toContain('p2__color-ff0000')
  })

  it('skips hidden layers', () => {
    const snap = snapshot('p1', 0, 0)
    snap.visibility['color-00ff00'] = false
    const result = buildComposite([snap], profile())
    expect(result.layers).toHaveLength(1)
    expect(result.layers[0]!.layer_id).toBe('p1__color-ff0000')
    // The hidden layer's group shouldn't appear in the SVG either
    expect(result.svg).not.toContain('p1__color-00ff00')
  })

  it('bakes a 90° rotation into a matrix transform with swapped extents', () => {
    // Placement: 100×100 viewBox rotated 90° CW, footprint 60mm × 40mm
    // after width/height swap done by the store. The viewBox H (100)
    // maps to the footprint W (60), so the linear part should be
    // (sx=0, sy=0.6) on the X row and (sx=0.4, sy=0) on the Y row.
    const snap = snapshot('p1', 100, 50, 60, 40)
    snap.rotation = 90
    const result = buildComposite([snap], profile())
    // 90° rotation routes through the ``matrix(...)`` branch (no
    // ``translate ... scale ...`` fast path).
    expect(result.svg).toContain('matrix(')
    // Layer (0,0)→(100,100) in viewBox maps to a 60×40 footprint at
    // (100, 50). The bbox should match the placement footprint.
    const composedRed = result.layers[0]!
    expect(composedRed.bbox.x_min).toBeCloseTo(100, 4)
    expect(composedRed.bbox.x_max).toBeCloseTo(160, 4)
    expect(composedRed.bbox.y_min).toBeCloseTo(50, 4)
    expect(composedRed.bbox.y_max).toBeCloseTo(90, 4)
  })

  it('bakes horizontal mirror by negating the X scale in the matrix', () => {
    const snap = snapshot('p1', 0, 0, 100, 100)
    snap.flip_h = true
    const result = buildComposite([snap], profile())
    // matrix(a b c d e f) — flipping H makes ``a`` negative.
    const match = result.svg.match(/matrix\(([-0-9.]+) ([-0-9.]+) ([-0-9.]+) ([-0-9.]+) ([-0-9.]+) ([-0-9.]+)\)/)
    expect(match).toBeTruthy()
    const [, a, , , d] = match!.map(Number)
    expect(a).toBeLessThan(0)
    expect(d).toBeGreaterThan(0)
    // Layer footprint stays within the placement rect even when mirrored.
    const composedRed = result.layers[0]!
    expect(composedRed.bbox.x_min).toBeCloseTo(0, 4)
    expect(composedRed.bbox.x_max).toBeCloseTo(100, 4)
  })

  it('emits each labeled group as a top-level child of the svg root', () => {
    // Regression: the prior implementation wrapped the placement's labeled
    // groups in an outer ``<g data-placement-id ...>`` carrying the
    // transform. The backend's ``labeled_group_fragments`` only inspects
    // direct ``<g>`` children of the ``<svg>`` root for ``inkscape:label``,
    // so the nested labels were invisible — every layer collapsed to a
    // single ``layer-1`` and per-layer overrides (pen slot, speed, pause)
    // never matched anything. The fix hoists each labeled group to the
    // top level with the placement transform applied directly.
    const result = buildComposite([snapshot('p1', 10, 20, 50, 50)], profile())
    // Parse the produced SVG and confirm every labeled group is a direct
    // child of the root.
    const doc = new DOMParser().parseFromString(result.svg, 'image/svg+xml')
    const root = doc.documentElement
    const labeled: string[] = []
    for (const child of Array.from(root.children)) {
      const label = child.getAttribute('inkscape:label')
      if (child.tagName.toLowerCase() === 'g' && label) labeled.push(label)
    }
    expect(labeled).toContain('p1__color-ff0000')
    expect(labeled).toContain('p1__color-00ff00')
    // Each labeled group carries the placement transform.
    for (const label of labeled) {
      const node = root.querySelector(`g[inkscape\\:label="${label}"]`)
      expect(node?.getAttribute('transform')).toBe('translate(10 20) scale(0.5 0.5)')
    }
  })

  it('wraps unlabeled source content in a synthetic ``layer-1`` group', () => {
    // Files that have no labeled groups (single-colour SVGs) still need
    // a labeled wrapper in the composite so the backend treats them as a
    // proper layer with the matching ``${p.id}__layer-1`` id, and so
    // per-layer overrides keyed on that id apply.
    const snap: PlacementSnapshot = {
      id: 'p1',
      svg:
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        + '<path d="M0 0 L100 100"/>'
        + '</svg>',
      layers: [{ ...layer('layer-1'), bbox: { x_min: 0, y_min: 0, x_max: 100, y_max: 100 } }],
      source_bbox: { x_min: 0, y_min: 0, x_max: 100, y_max: 100 },
      visibility: { 'layer-1': true },
      x_mm: 0,
      y_mm: 0,
      width_mm: 100,
      height_mm: 100,
    }
    const result = buildComposite([snap], profile())
    const doc = new DOMParser().parseFromString(result.svg, 'image/svg+xml')
    const root = doc.documentElement
    const labels = Array.from(root.children)
      .map((c) => c.getAttribute('inkscape:label'))
      .filter((l): l is string => Boolean(l))
    expect(labels).toContain('p1__layer-1')
  })

  it('scales the source bbox into workspace coordinates', () => {
    const result = buildComposite([snapshot('p1', 50, 50, 200, 100)], profile())
    const composedRed = result.layers[0]!
    // Source bbox was 100×100; placement is 200×100 → sx=2, sy=1
    expect(composedRed.bbox.x_min).toBeCloseTo(50, 6)
    expect(composedRed.bbox.x_max).toBeCloseTo(250, 6)
    expect(composedRed.bbox.y_min).toBeCloseTo(50, 6)
    expect(composedRed.bbox.y_max).toBeCloseTo(150, 6)
    // total_length scales by sqrt(sx*sy) = sqrt(2) ≈ 1.414
    expect(composedRed.total_length_mm).toBeCloseTo(100 * Math.SQRT2, 4)
  })
})
