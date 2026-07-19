// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'
import type { WorkflowStep } from '../composables/useWorkflowStep'

// Drive the bar through a controllable step ref — the state derivation
// itself is covered by useWorkflowStep.test.ts; this file owns the
// label mapping + action dispatch contract.
const stepRef = ref<WorkflowStep>('empty')
vi.mock('../composables/useWorkflowStep', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../composables/useWorkflowStep')>()
  return { ...actual, useWorkflowStep: () => ({ step: computed(() => stepRef.value) }) }
})

const launch = vi.fn()
vi.mock('../composables/useLaunchCurrentJob', () => ({
  useLaunchCurrentJob: () => ({ launch }),
}))

import PrimaryWorkflowAction from './PrimaryWorkflowAction.vue'
import { useUiStore } from '../stores/ui'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      workflow: {
        addFile: 'Add a file',
        hintAddFile: 'Library empty.',
        addToPlan: 'Add to plan',
        hintAddToPlan: 'Nothing placed.',
        chooseStyle: 'Choose the style',
        hintChooseStyle: 'No style yet.',
        fixPens: 'Fix pens',
        hintFixPens: 'Pens missing.',
        verify: 'Check the plot',
        hintVerify: 'Generate + review.',
        connect: 'Connect the plotter',
        hintConnect: 'Machine missing.',
        launch: 'Start the plot',
        hintLaunch: 'All set.',
        pause: 'Pause',
        hintRunning: 'Printing.',
        resume: 'Resume',
        hintPaused: 'Paused.',
      },
      plotter: { stop: 'Stop' },
    },
  },
})

function mountBar() {
  return mount(PrimaryWorkflowAction, { global: { plugins: [i18n] } })
}

describe('PrimaryWorkflowAction', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    stepRef.value = 'empty'
    launch.mockReset()
  })

  it('maps each step to its primary label; Stop only appears during a run', async () => {
    const wrapper = mountBar()
    const cases: Array<[WorkflowStep, string, boolean]> = [
      ['empty', 'Add a file', false],
      ['imported', 'Add to plan', false],
      ['placed', 'Choose the style', false],
      ['preflight_blocked', 'Fix pens', false],
      ['configured', 'Check the plot', false],
      ['ready_disconnected', 'Connect the plotter', false],
      ['ready', 'Start the plot', false],
      ['running', 'Pause', true],
      ['paused', 'Resume', true],
    ]
    for (const [step, label, stop] of cases) {
      stepRef.value = step
      await wrapper.vm.$nextTick()
      expect(wrapper.find('[data-test="workflow-primary"]').text()).toBe(label)
      expect(wrapper.find('[data-test="workflow-stop"]').exists()).toBe(stop)
    }
  })

  it('empty → asks FilesPane to open the file picker', async () => {
    const wrapper = mountBar()
    const ui = useUiStore()
    await wrapper.find('[data-test="workflow-primary"]').trigger('click')
    expect(ui.addFileRequests).toBe(1)
  })

  it('preflight_blocked → opens plotter settings on the colours tab', async () => {
    stepRef.value = 'preflight_blocked'
    const wrapper = mountBar()
    const ui = useUiStore()
    await wrapper.find('[data-test="workflow-primary"]').trigger('click')
    expect(ui.plotterSettingsOpen).toBe(true)
    expect(ui.plotterTab).toBe('colors')
  })

  it('ready → routes through the shared launch path', async () => {
    stepRef.value = 'ready'
    const wrapper = mountBar()
    await wrapper.find('[data-test="workflow-primary"]').trigger('click')
    expect(launch).toHaveBeenCalledTimes(1)
  })
})
