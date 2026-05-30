// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { LayerInfo } from '../../api/client'
import type { PolicyDecision } from '../../domain/policy/schemas'
import LayerInspector from './LayerInspector.vue'
import PipelineInspector from './PipelineInspector.vue'

function makeLayer(over: Partial<LayerInfo> = {}): LayerInfo {
  return {
    layer_id: 'l1',
    source_color: '#ff0000',
    target_pen_slot: 1,
    draw_order: 0,
    total_length_mm: 120.0,
    path_count: 4,
    bbox: { x_min: 0, y_min: 0, x_max: 10, y_max: 10 },
    optimize: true,
    simplify_tolerance_mm: 0.05,
    drawing_speed_mm_s: null,
    color_label: null,
    pause_before: 'auto',
    assigned_color_hex: null,
    assigned_color_source: 'auto',
    layer_passes: [],
    ...over,
  } as unknown as LayerInfo
}

const decision: PolicyDecision = {
  segmentation_method: 'fixed_palette',
  default_algorithm: 'scanlines',
  default_options: { spacing_px: 5, num_colors: 4 },
  default_passes: [],
  quality_tier: 'draft',
  fallback_chain: ['halftone'],
  reasoning: [{ rule: 'bitmap_photo.fast', description: 'photo + fast' }],
  hard_constraints_applied: [
    {
      constraint: 'sparse_palette',
      description: 'palette ≤ 2',
      forbidden_algorithms: [],
    },
  ],
}

describe('LayerInspector', () => {
  it('renders one row per layer in draw_order', () => {
    const layers = [
      makeLayer({ layer_id: 'a', draw_order: 1, target_pen_slot: 2 }),
      makeLayer({ layer_id: 'b', draw_order: 0, target_pen_slot: 1 }),
    ]
    const wrapper = mount(LayerInspector, { props: { layers } })
    const rows = wrapper.findAll('tbody tr')
    expect(rows.length).toBe(2)
    // 'b' has draw_order 0 → appears first.
    expect(rows[0]?.attributes('data-test')).toBe('layer-row-b')
  })

  it('counts swaps using the pause policy', () => {
    const layers = [
      makeLayer({ layer_id: 'a', draw_order: 0, target_pen_slot: 1 }),
      makeLayer({ layer_id: 'b', draw_order: 1, target_pen_slot: 2 }), // +1 (slot change, auto)
      makeLayer({ layer_id: 'c', draw_order: 2, target_pen_slot: 2, pause_before: 'always' }), // +1
      makeLayer({ layer_id: 'd', draw_order: 3, target_pen_slot: 3, pause_before: 'never' }), // 0
    ]
    const wrapper = mount(LayerInspector, { props: { layers } })
    expect(wrapper.text()).toContain('2 changement(s) stylo')
  })

  it('sums total draw length from layers when not provided', () => {
    const layers = [
      makeLayer({ layer_id: 'a', total_length_mm: 50, draw_order: 0 }),
      makeLayer({ layer_id: 'b', total_length_mm: 70, draw_order: 1 }),
    ]
    const wrapper = mount(LayerInspector, { props: { layers } })
    // 120 mm → 12 cm
    expect(wrapper.text()).toContain('12 cm')
  })
})

describe('PipelineInspector', () => {
  it('shows empty hint when no decision is supplied', () => {
    const wrapper = mount(PipelineInspector, { props: { decision: null } })
    expect(wrapper.find('[data-test="pipeline-empty"]').exists()).toBe(true)
  })

  it('renders the segmentation + algorithm chain', () => {
    const wrapper = mount(PipelineInspector, {
      props: { decision, sourceKind: 'bitmap_photo' },
    })
    expect(wrapper.find('[data-test="pipeline-segmentation"]').text()).toBe('fixed_palette')
    expect(wrapper.find('[data-test="pipeline-algorithm"]').text()).toBe('scanlines')
  })

  it('lists hard constraints with their constraint code', () => {
    const wrapper = mount(PipelineInspector, {
      props: { decision, sourceKind: 'bitmap_photo' },
    })
    expect(wrapper.find('[data-test="pipeline-constraint-sparse_palette"]').exists()).toBe(true)
  })

  it('renders the fallback chain when present', () => {
    const wrapper = mount(PipelineInspector, {
      props: { decision, sourceKind: 'bitmap_photo' },
    })
    expect(wrapper.text()).toContain('halftone')
  })
})
