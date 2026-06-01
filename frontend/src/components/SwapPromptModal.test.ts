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
        resume: 'I changed the pen — Resume',
        cancel: 'Cancel run',
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
})
