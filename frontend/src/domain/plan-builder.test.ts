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
    assigned_color_hex: null,
    color_assignment: 'auto',
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
      optimize: true,
      simplify_tolerance_mm: 0.05,
      assigned_color_hex: null,
    })
  })

  it('preserves null pen slot and speed', () => {
    const plan = toLayerPlan(layer({ target_pen_slot: null, drawing_speed_mm_s: null }))
    expect(plan.target_pen_slot).toBeNull()
    expect(plan.drawing_speed_mm_s).toBeNull()
  })

  it('forwards optimize=false through the projection', () => {
    // Regression guard for the L2 audit finding: editing this flag in
    // the UI used to leave no trace in the plan sent to /preflight or
    // /generate. It now rides along into the plan and the plan_hash.
    const plan = toLayerPlan(layer({ optimize: false, simplify_tolerance_mm: 0.2 }))
    expect(plan.optimize).toBe(false)
    expect(plan.simplify_tolerance_mm).toBe(0.2)
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

  it('forwards typography into the PrintPlan when supplied', () => {
    // Regression guard for the L5 audit finding: font / size / bold /
    // italic edits used to leave no trace in the plan sent to
    // /preflight or /generate. They now ride along into the plan and
    // the plan_hash.
    const plan = buildPrintPlan({
      svg: '<svg/>',
      profileName: 'Test',
      layers: [],
      placement: null,
      typography: {
        font: 'rowmant',
        font_size_mm: 18,
        page_width_mm: 210,
        page_height_mm: 297,
        margin_mm: 15,
        line_spacing: 1.5,
        alignment: 'left',
        stroke_width_mm: 0.3,
        bold: true,
        italic: false,
        letter_spacing_mm: 0,
      },
    })
    expect(plan.typography?.font).toBe('rowmant')
    expect(plan.typography?.font_size_mm).toBe(18)
    expect(plan.typography?.bold).toBe(true)
  })

  it('omits typography (null) for non-text sources', () => {
    const plan = buildPrintPlan({
      svg: '<svg/>',
      profileName: 'Test',
      layers: [],
      placement: null,
    })
    expect(plan.typography).toBeNull()
  })

  it('forwards libraryFileId + sourceMime so backend can rerender text', () => {
    // The post-L5 in-pipeline text rerender path engages only when
    // these two are non-null AND the typography block is present.
    // Pin the projection: a future store change that forgets to pass
    // them through would silently revert to the upload-time render.
    const plan = buildPrintPlan({
      svg: '<svg/>',
      profileName: 'Test',
      layers: [],
      placement: null,
      libraryFileId: 'lib-abc',
      sourceMime: 'text/plain',
    })
    expect(plan.library_file_id).toBe('lib-abc')
    expect(plan.source_mime).toBe('text/plain')
  })

  it('defaults libraryFileId + sourceMime to null when omitted', () => {
    // Backwards compat: non-text placements never populate these so
    // the plan must serialise them as ``null`` rather than ``undefined``
    // (the backend Pydantic model rejects unknown / missing-required
    // discriminators on strict-mode endpoints).
    const plan = buildPrintPlan({
      svg: '<svg/>',
      profileName: 'Test',
      layers: [],
      placement: null,
    })
    expect(plan.library_file_id).toBeNull()
    expect(plan.source_mime).toBeNull()
  })
})
