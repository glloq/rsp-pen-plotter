// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

vi.mock('../api/client', async (orig) => {
  const actual = await orig<typeof import('../api/client')>()
  return {
    ...actual,
    listQueue: vi.fn(async () => []),
    listGcodeFiles: vi.fn(async () => []),
  }
})

import en from '../locales/en.json'
import PlotterControl from './PlotterControl.vue'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'
import type { MachineProfile } from '../api/client'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en },
})

function makeProfile(): MachineProfile {
  return {
    name: 'Test A3',
    units: 'mm',
    workspace: { x_min: 0, y_min: 0, x_max: 297, y_max: 420 },
    origin: 'bottom_left',
    gcode_dialect: 'grbl',
    pen_up_command: 'M3 S0',
    pen_down_command: 'M3 S1000',
    tool_change_method: 'manual_pause',
    tool_change_command: 'M0',
    drawing_speed_mm_s: 30,
    travel_speed_mm_s: 80,
    acceleration_mm_s2: 500,
    pen_lift_time_ms: 0,
    pen_slot_count: 1,
    supports_arcs: false,
    arc_tolerance_mm: 0.1,
    ebb: null,
    pens: null,
  } as MachineProfile
}

async function seedProfile(): Promise<void> {
  const job = useJobStore()
  const { profiles, selectedProfileName } = storeToRefs(job)
  profiles.value = [makeProfile()]
  selectedProfileName.value = 'Test A3'
  await nextTick()
}

function mountControl() {
  return mount(PlotterControl, { global: { plugins: [i18n] } })
}

describe('PlotterControl — manual control always visible', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders the manual controls even while disconnected, greyed + disabled', async () => {
    await seedProfile()
    expect(usePlotterStore().status.connected).toBe(false)
    const wrapper = mountControl()
    await nextTick()

    // The control surface is mounted (no longer hidden behind an empty state).
    expect(wrapper.find('[data-test="manual-control"]').exists()).toBe(true)
    // A connect shortcut surfaces in the toolbar while offline.
    expect(wrapper.find('[data-test="plotter-connect-cta"]').exists()).toBe(true)

    // Pen + jog controls are present but disabled.
    expect(wrapper.find('[data-test="manual-pen-up"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="manual-pen-down"]').attributes('disabled')).toBeDefined()
    const jogUp = wrapper.find('button[aria-label="Jog up (Y+)"]')
    expect(jogUp.exists()).toBe(true)
    expect(jogUp.attributes('disabled')).toBeDefined()
    const home = wrapper.find('[data-test="home-all"]')
    expect(home.attributes('disabled')).toBeDefined()
  })

  it('enables the controls and hides the connect banner once connected', async () => {
    await seedProfile()
    usePlotterStore().status.connected = true
    const wrapper = mountControl()
    await nextTick()

    // The connect shortcut disappears once connected.
    expect(wrapper.find('[data-test="plotter-connect-cta"]').exists()).toBe(false)
    // Pen commands are set on the profile, so connection is the only gate.
    expect(wrapper.find('[data-test="manual-pen-up"]').attributes('disabled')).toBeUndefined()
    const jogUp = wrapper.find('button[aria-label="Jog up (Y+)"]')
    expect(jogUp.attributes('disabled')).toBeUndefined()
  })

  it('keeps manual controls disabled while a job owns the head (running)', async () => {
    await seedProfile()
    const plotter = usePlotterStore()
    plotter.status.connected = true
    plotter.status.state = 'running'
    const wrapper = mountControl()
    await nextTick()

    expect(wrapper.find('[data-test="manual-pen-up"]').attributes('disabled')).toBeDefined()
    const jogUp = wrapper.find('button[aria-label="Jog up (Y+)"]')
    expect(jogUp.attributes('disabled')).toBeDefined()
  })

  it('shows the workshop camera slot above the manual controls', async () => {
    await seedProfile()
    const wrapper = mountControl()
    await nextTick()

    // The camera feed lives at the top of the tab; with no camera
    // configured it renders its configure-hint state.
    expect(wrapper.find('[data-test="camera-view"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="camera-configure"]').exists()).toBe(true)
  })
})
