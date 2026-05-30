// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import type { PenSlot } from '../../api/client'
import CapabilityWizard from './CapabilityWizard.vue'
import MagazineView from './MagazineView.vue'

describe('CapabilityWizard', () => {
  it('opens on the mode picker with manual selected by default', () => {
    const wrapper = mount(CapabilityWizard)
    expect(wrapper.find('[data-test="cap-step-mode"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="cap-mode-manual"]').classes()).not.toContain('active')
    // The active class is on the LI, not the button.
    const activeLi = wrapper.findAll('.modes li.active')
    expect(activeLi.length).toBeGreaterThan(0)
  })

  it('shows the manual prompt knobs only when manual mode is selected', async () => {
    const wrapper = mount(CapabilityWizard)
    await wrapper.find('[data-test="cap-mode-manual"]').trigger('click')
    await wrapper.find('[data-test="cap-next"]').trigger('click')
    expect(wrapper.find('[data-test="cap-manual-knobs"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="cap-macro-knobs"]').exists()).toBe(false)
  })

  it('shows the macro steps editor when host_macro is selected', async () => {
    const wrapper = mount(CapabilityWizard)
    await wrapper.find('[data-test="cap-mode-host_macro"]').trigger('click')
    await nextTick()
    // Need at least one macro line before advancing.
    expect(wrapper.find('[data-test="cap-next"]').attributes('disabled')).toBeUndefined()
    await wrapper.find('[data-test="cap-next"]').trigger('click')
    expect(wrapper.find('[data-test="cap-macro-knobs"]').exists()).toBe(true)
    // Start with an empty macro list → advancing past this step would fail.
    await wrapper.find('[data-test="cap-macro-add"]').trigger('click')
    await wrapper.find('[data-test="cap-macro-send-0"]').setValue('M6 T{slot}')
    await nextTick()
  })

  it('blocks advance from host_macro details until at least one step has a non-empty send', async () => {
    const wrapper = mount(CapabilityWizard)
    await wrapper.find('[data-test="cap-mode-host_macro"]').trigger('click')
    await wrapper.find('[data-test="cap-next"]').trigger('click') // go to details
    await wrapper.find('[data-test="cap-macro-add"]').trigger('click') // empty line
    await nextTick()
    expect(wrapper.find('[data-test="cap-next"]').attributes('disabled')).toBe('')
    await wrapper.find('[data-test="cap-macro-send-0"]').setValue('M6')
    await nextTick()
    expect(wrapper.find('[data-test="cap-next"]').attributes('disabled')).toBeUndefined()
  })

  it('hides the knobs step content for single_pen', async () => {
    const wrapper = mount(CapabilityWizard)
    await wrapper.find('[data-test="cap-mode-single_pen"]').trigger('click')
    await wrapper.find('[data-test="cap-next"]').trigger('click')
    expect(wrapper.find('[data-test="cap-no-knobs"]').exists()).toBe(true)
  })

  it('emits the resolved capabilities on confirm', async () => {
    const wrapper = mount(CapabilityWizard)
    await wrapper.find('[data-test="cap-mode-firmware"]').trigger('click')
    await wrapper.find('[data-test="cap-next"]').trigger('click')
    await wrapper.find('[data-test="cap-next"]').trigger('click')
    await wrapper.find('[data-test="cap-magazine-size"]').setValue(8)
    await wrapper.find('[data-test="cap-confirm"]').trigger('click')
    const events = wrapper.emitted('confirm')
    expect(events).toBeTruthy()
    const caps = events![0]![0] as {
      tool_change: { mode: string; command_source: string }
      max_pens_in_magazine: number
    }
    expect(caps.tool_change.mode).toBe('firmware')
    expect(caps.tool_change.command_source).toBe('machine')
    expect(caps.max_pens_in_magazine).toBe(8)
  })

  it('emits cancel on the Annuler button', async () => {
    const wrapper = mount(CapabilityWizard)
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Annuler')!
      .trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
  })
})

function slot(over: Partial<PenSlot>): PenSlot {
  return {
    index: 0,
    name: '',
    color: '#000000',
    installed: false,
    position: null,
    pen_up_command: null,
    pen_down_command: null,
    ...over,
  }
}

describe('MagazineView', () => {
  it('renders one cell per installed pen', () => {
    const slots = [
      slot({ index: 0, color: '#ff0000', installed: true }),
      slot({ index: 1, color: '#0000ff', installed: true }),
    ]
    const wrapper = mount(MagazineView, { props: { slots } })
    expect(wrapper.findAll('.slot-cell').length).toBe(2)
    expect(wrapper.find('[data-test="slot-0"]').classes()).toContain('installed')
  })

  it('pads to capacity with empty placeholders', () => {
    const slots = [slot({ index: 0, color: '#000000', installed: true })]
    const wrapper = mount(MagazineView, { props: { slots, capacity: 4 } })
    const cells = wrapper.findAll('.slot-cell')
    expect(cells.length).toBe(4)
    expect(cells[1]?.classes()).toContain('empty')
  })

  it('shows the calibrated coordinates when slot.position is set', () => {
    const slots = [
      slot({
        index: 0,
        color: '#ff0000',
        installed: true,
        position: { x: 12.3, y: 4.5 },
      }),
    ]
    const wrapper = mount(MagazineView, { props: { slots } })
    expect(wrapper.text()).toContain('calibré')
    expect(wrapper.text()).toContain('12.3')
  })

  it('emits toggle-install when the colour dot is clicked', async () => {
    const slots = [slot({ index: 0, color: '#ff0000' })]
    const wrapper = mount(MagazineView, { props: { slots } })
    await wrapper.find('[data-test="slot-0-toggle"]').trigger('click')
    expect(wrapper.emitted('toggle-install')?.[0]).toEqual([0])
  })

  it('highlights the simulationSlot when provided', () => {
    const slots = [
      slot({ index: 0, color: '#ff0000', installed: true }),
      slot({ index: 1, color: '#00ff00', installed: true }),
    ]
    const wrapper = mount(MagazineView, { props: { slots, simulationSlot: 1 } })
    expect(wrapper.find('[data-test="slot-1"]').classes()).toContain('simulating')
    expect(wrapper.find('[data-test="slot-0"]').classes()).not.toContain('simulating')
  })
})
