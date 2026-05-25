// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import MachineStatusPill from './MachineStatusPill.vue'
import { usePlotterStore } from '../stores/plotter'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      machine: {
        disconnected: 'Offline',
        idle: 'Ready',
        running: 'Running',
        paused: 'Paused',
        toolChange: 'Pen change',
        error: 'Error',
        done: 'Done',
        aborted: 'Aborted',
      },
    },
  },
})

function mountPill() {
  return mount(MachineStatusPill, { global: { plugins: [i18n] } })
}

describe('MachineStatusPill', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('shows Offline when the plotter is not connected', () => {
    // Default plotter store state has connected=false. The pill must
    // make that immediately legible — disconnect is the most common
    // state on a fresh page load and should be distinguishable from
    // "idle but connected" at a glance.
    const wrapper = mountPill()
    expect(wrapper.text()).toContain('Offline')
    expect(wrapper.classes().join(' ')).toContain('text-slate-400')
  })

  it('shows Ready when connected + idle', () => {
    const plotter = usePlotterStore()
    plotter.status.connected = true
    plotter.status.state = 'idle'
    const wrapper = mountPill()
    expect(wrapper.text()).toContain('Ready')
    expect(wrapper.classes().join(' ')).toContain('text-emerald-200')
  })

  it('shows Running with a percent suffix while a job is in flight', () => {
    const plotter = usePlotterStore()
    plotter.status.connected = true
    plotter.status.state = 'running'
    plotter.status.total = 200
    plotter.status.acked = 50 // 25%
    const wrapper = mountPill()
    expect(wrapper.text()).toContain('Running')
    expect(wrapper.text()).toContain('25%')
    expect(wrapper.classes().join(' ')).toContain('text-sky-200')
  })

  it('switches to a warning tone for paused / waiting / error / aborted', () => {
    const plotter = usePlotterStore()
    plotter.status.connected = true
    for (const state of ['paused', 'waiting', 'error', 'aborted'] as const) {
      plotter.status.state = state
      const wrapper = mountPill()
      expect(wrapper.classes().join(' ')).toContain('text-amber-200')
    }
  })

  it('falls back to idle styling for the Done terminal state', () => {
    // Done is a quiet success — it shouldn't read as "still running"
    // or as a warning. The pill stays in idle tone.
    const plotter = usePlotterStore()
    plotter.status.connected = true
    plotter.status.state = 'done'
    const wrapper = mountPill()
    expect(wrapper.text()).toContain('Done')
    expect(wrapper.classes().join(' ')).toContain('text-emerald-200')
  })
})
