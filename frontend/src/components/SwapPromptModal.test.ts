// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SwapPromptModal from './SwapPromptModal.vue'
import { useQueueStore } from '../stores/queue'
import type { PrintRun } from '../api/client'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      swap: {
        title: 'Pen change required',
        parkedHint: 'The head has parked.',
        slotBadge: 'Slot {slot}',
        resume: 'I changed the pen — Resume',
        cancel: 'Cancel run',
        msg: {
          toolChange: 'Insert {label} into pen slot {slot}, then resume.',
          colorChange: 'Change the pen to {label}, then resume.',
          load: 'Load {label} into magazine slot {slot}, then resume.',
        },
      },
    },
  },
})

function run(overrides: Partial<PrintRun> = {}): PrintRun {
  return {
    id: 'r1',
    name: 'job',
    profile_name: 'p',
    gcode: '',
    total_lines: 10,
    acked_lines: 3,
    state: 'paused',
    priority: 0,
    error: null,
    swap_prompt: 'Change pen to Red (#ff0000)',
    created_at: '',
    updated_at: '',
    ...overrides,
  } as PrintRun
}

function mountModal() {
  return mount(SwapPromptModal, { global: { plugins: [i18n] } })
}

describe('SwapPromptModal', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('shows the prompt when a run is paused for a swap', () => {
    const queue = useQueueStore()
    queue.runs = [run()]
    const wrapper = mountModal()
    expect(wrapper.find('[data-test="swap-prompt-modal"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="swap-prompt-text"]').text()).toContain('Red')
  })

  it('stays hidden for a plain pause with no swap prompt', () => {
    const queue = useQueueStore()
    queue.runs = [run({ swap_prompt: null })]
    const wrapper = mountModal()
    expect(wrapper.find('[data-test="swap-prompt-modal"]').exists()).toBe(false)
  })

  it('stays hidden while the run is still running', () => {
    const queue = useQueueStore()
    queue.runs = [run({ state: 'running' })]
    const wrapper = mountModal()
    expect(wrapper.find('[data-test="swap-prompt-modal"]').exists()).toBe(false)
  })

  it('resumes the run through the queue store', async () => {
    const queue = useQueueStore()
    queue.runs = [run()]
    const act = vi.spyOn(queue, 'act').mockResolvedValue()
    const wrapper = mountModal()
    await wrapper.find('[data-test="swap-resume"]').trigger('click')
    expect(act).toHaveBeenCalledWith('r1', 'resume')
  })

  it('renders a swatch parsed from the prompt hex', () => {
    const queue = useQueueStore()
    queue.runs = [run({ swap_prompt: 'Insert pen slot 2: Vert prairie #00ff00' })]
    const wrapper = mountModal()
    expect(wrapper.find('[data-test="swap-prompt-slot"]').text()).toBe('Slot 2')
    const swatch = wrapper.find('[data-test="swap-prompt-swatch"]')
    expect(swatch.exists()).toBe(true)
    expect((swatch.element as HTMLElement).style.backgroundColor).toBe('#00ff00')
  })

  it('prefers the structured swap_slot over parsing the prompt text', () => {
    const queue = useQueueStore()
    // Prompt names slot 2, but the structured field says 5 — the backend
    // field wins so a localised prompt can never mislead the badge.
    queue.runs = [run({ swap_prompt: 'Insert pen slot 2: Red #ff0000', swap_slot: 5 })]
    const wrapper = mountModal()
    expect(wrapper.find('[data-test="swap-prompt-slot"]').text()).toBe('Slot 5')
  })

  it('composes a localised prompt from the structured fields when present', () => {
    const queue = useQueueStore()
    queue.runs = [
      run({
        swap_prompt: 'Insert pen slot 2: Vert prairie #00ff00',
        swap_slot: 2,
        swap_label: 'Vert prairie',
        swap_color: '#00ff00',
        swap_reason: 'tool_change',
      }),
    ]
    const wrapper = mountModal()
    expect(wrapper.find('[data-test="swap-prompt-text"]').text()).toBe(
      'Insert Vert prairie into pen slot 2, then resume.',
    )
    // Swatch driven by the structured hex, not by text parsing.
    expect(
      (wrapper.find('[data-test="swap-prompt-swatch"]').element as HTMLElement).style
        .backgroundColor,
    ).toBe('#00ff00')
  })

  it('keeps the backend prompt for runs without structured fields', () => {
    const queue = useQueueStore()
    queue.runs = [run({ swap_prompt: 'Change pen to Red (#ff0000)' })]
    const wrapper = mountModal()
    expect(wrapper.find('[data-test="swap-prompt-text"]').text()).toBe(
      'Change pen to Red (#ff0000)',
    )
  })

  it('composes the load message for a magazine-load boundary', () => {
    const queue = useQueueStore()
    queue.runs = [
      run({
        swap_prompt: 'Load Rouge into magazine slot 1, then press Resume.',
        swap_slot: 1,
        swap_label: 'Rouge',
        swap_color: '#ff0011',
        swap_reason: 'load',
      }),
    ]
    const wrapper = mountModal()
    expect(wrapper.find('[data-test="swap-prompt-text"]').text()).toBe(
      'Load Rouge into magazine slot 1, then resume.',
    )
  })

  it('falls back to an inventory name match when the prompt has no hex', async () => {
    const { useAvailableColorsStore } = await import('../stores/availableColors')
    const inventory = useAvailableColorsStore()
    inventory.colors = [
      {
        id: '1',
        hex: '#123456',
        name: 'Bleu nuit',
        position: 0,
        created_at: '2026-01-01T00:00:00Z',
      },
    ] as never
    const queue = useQueueStore()
    queue.runs = [run({ swap_prompt: 'Insert pen slot 1: Bleu nuit' })]
    const wrapper = mountModal()
    expect(wrapper.find('[data-test="swap-prompt-slot"]').text()).toBe('Slot 1')
    expect(
      (wrapper.find('[data-test="swap-prompt-swatch"]').element as HTMLElement).style
        .backgroundColor,
    ).toBe('#123456')
  })
})
