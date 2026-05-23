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
