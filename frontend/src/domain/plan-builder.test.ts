import { describe, expect, it } from 'vitest'
import type { LayerInfo } from '../api/client'
import { buildPrintPlan, toLayerPlan } from './plan-builder'

function layer(overrides: Partial<LayerInfo> = {}): LayerInfo {
  return {
    layer_id: 'red',
    source_color: '#ff0000',
    target_pen_slot: 0,
    draw_order: 0,
    total_length_mm: 100,
    path_count: 1,
    bbox: { x_min: 0, y_min: 0, x_max: 10, y_max: 10 },
    optimize: true,
    simplify_tolerance_mm: 0.05,
    drawing_speed_mm_s: 60,
    color_label: 'Red',
    pause_before: 'auto',
    ...overrides,
  }
}

describe('toLayerPlan', () => {
  // The most important contract: every field the backend's ``LayerPlan``
  // declares is set by this projection. If a future migration adds a
  // field on the backend but forgets the frontend mapping, this test
  // (combined with TypeScript checking ``api-types.ts``) is the safety
  // net that catches it.
  it('projects every backend layer field from a LayerInfo', () => {
    const plan = toLayerPlan(layer())
    expect(plan).toEqual({
      layer_id: 'red',
      target_pen_slot: 0,
      drawing_speed_mm_s: 60,
      source_color: '#ff0000',
      color_label: 'Red',
      pause_before: 'auto',
    })
  })

  it('preserves null pen slot and speed', () => {
    const plan = toLayerPlan(layer({ target_pen_slot: null, drawing_speed_mm_s: null }))
    expect(plan.target_pen_slot).toBeNull()
    expect(plan.drawing_speed_mm_s).toBeNull()
  })
})

describe('buildPrintPlan', () => {
  it('routes all the inputs into a backend-shaped PrintPlan', () => {
    const plan = buildPrintPlan({
      svg: '<svg/>',
      profileName: 'Test',
      layers: [layer({ layer_id: 'red' }), layer({ layer_id: 'blue', target_pen_slot: 1 })],
      placement: {
        sheet_width_mm: 200,
        sheet_height_mm: 150,
        offset_x_mm: 10,
        offset_y_mm: 5,
      },
    })
    expect(plan.svg).toBe('<svg/>')
    expect(plan.profile_name).toBe('Test')
    expect(plan.scale_mode).toBe('actual')
    expect(plan.margin_mm).toBe(0)
    expect(plan.layers).toHaveLength(2)
    expect(plan.layers?.[1]?.target_pen_slot).toBe(1)
    expect(plan.placement?.sheet_width_mm).toBe(200)
  })

  it('builds the same layer projection regardless of where the plan is used', () => {
    // Mirrors the property the backend ``resolve_plan`` guarantees:
    // the SAME ``LayerInfo[]`` produces the SAME on-wire layer list.
    const layers = [layer(), layer({ layer_id: 'green', target_pen_slot: 2 })]
    const planA = buildPrintPlan({ svg: 'x', profileName: 'P', layers, placement: null })
    const planB = buildPrintPlan({ svg: 'x', profileName: 'P', layers, placement: null })
    expect(planA.layers).toEqual(planB.layers)
  })
})
