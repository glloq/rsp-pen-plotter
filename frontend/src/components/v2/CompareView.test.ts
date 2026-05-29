// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { PolicyDecision } from '../../domain/policy/schemas'
import CompareView, { type Candidate, type OverlayKey } from './CompareView.vue'

const decisionA: PolicyDecision = {
  segmentation_method: 'fixed_palette',
  default_algorithm: 'scanlines',
  default_options: {},
  default_passes: [],
  quality_tier: 'draft',
  fallback_chain: [],
  reasoning: [],
  hard_constraints_applied: [],
}
const decisionB: PolicyDecision = { ...decisionA, default_algorithm: 'stippling' }

function candidate(id: 'a' | 'b', metrics: Record<string, number>): Candidate {
  return {
    id,
    label: id.toUpperCase(),
    svg: `<svg xmlns="http://www.w3.org/2000/svg"></svg>`,
    decision: id === 'a' ? decisionA : decisionB,
    metrics,
  }
}

describe('CompareView', () => {
  it('renders both candidates and the metrics table', () => {
    const wrapper = mount(CompareView, {
      props: {
        a: candidate('a', { est_time_s: 90, draw_length_mm: 1000, swap_count: 1 }),
        b: candidate('b', { est_time_s: 60, draw_length_mm: 1200, swap_count: 2 }),
      },
    })
    expect(wrapper.find('[data-test="candidate-a"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="candidate-b"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="metrics-table"]').exists()).toBe(true)
  })

  it('marks the faster candidate as winner on Temps estimé', () => {
    const wrapper = mount(CompareView, {
      props: {
        a: candidate('a', { est_time_s: 90 }),
        b: candidate('b', { est_time_s: 60 }),
      },
    })
    const rows = wrapper.findAll('tbody tr')
    const timeRow = rows[0]!
    const cells = timeRow.findAll('td')
    expect(cells[0]!.classes()).not.toContain('winner')
    expect(cells[1]!.classes()).toContain('winner')
  })

  it('marks the candidate with shorter draw_length as winner', () => {
    const wrapper = mount(CompareView, {
      props: {
        a: candidate('a', { draw_length_mm: 800 }),
        b: candidate('b', { draw_length_mm: 1200 }),
      },
    })
    // Second row = "Longueur tracé".
    const rows = wrapper.findAll('tbody tr')
    const cells = rows[1]!.findAll('td')
    expect(cells[0]!.classes()).toContain('winner')
    expect(cells[1]!.classes()).not.toContain('winner')
  })

  it('emits pick-winner with the candidate id on Choisir', async () => {
    const wrapper = mount(CompareView, {
      props: {
        a: candidate('a', {}),
        b: candidate('b', {}),
      },
    })
    await wrapper.find('[data-test="pick-b"]').trigger('click')
    expect(wrapper.emitted('pick-winner')?.[0]).toEqual(['b'])
  })

  it('emits toggle-overlay when a checkbox changes', async () => {
    const wrapper = mount(CompareView, {
      props: {
        a: candidate('a', {}),
        b: candidate('b', {}),
      },
    })
    await wrapper
      .find('[data-test="overlay-penup_heatmap"] input')
      .trigger('change')
    expect(wrapper.emitted('toggle-overlay')?.[0]).toEqual(['penup_heatmap'])
  })

  it('renders the overlay stub list when overlays are enabled', () => {
    const overlays: OverlayKey[] = ['penup_heatmap', 'bounds']
    const wrapper = mount(CompareView, {
      props: {
        a: candidate('a', {}),
        b: candidate('b', {}),
        overlays,
      },
    })
    const stubs = wrapper.findAll('.overlay-stub')
    expect(stubs.length).toBe(2) // one stub per candidate
    expect(stubs[0]!.text()).toContain('penup_heatmap')
    expect(stubs[0]!.text()).toContain('bounds')
  })

  it('handles undefined metrics with em-dash', () => {
    const wrapper = mount(CompareView, {
      props: {
        a: candidate('a', {}),
        b: candidate('b', { est_time_s: 30 }),
      },
    })
    expect(wrapper.text()).toContain('—')
  })
})
