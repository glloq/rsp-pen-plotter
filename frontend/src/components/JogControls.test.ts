// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

const status = {
  connected: true,
  total: 0,
  sent: 0,
  acked: 0,
  state: 'idle' as const,
  message: null,
}

vi.mock('../api/client', async (orig) => {
  const actual = await orig<typeof import('../api/client')>()
  return {
    ...actual,
    plotterJog: vi.fn(async () => status),
    plotterRun: vi.fn(async () => status),
    plotterHome: vi.fn(async () => status),
  }
})
// Home goes through a confirm dialog — auto-confirm it.
vi.mock('../composables/confirm', () => ({ confirmAction: vi.fn(async () => true) }))

import en from '../locales/en.json'
import * as client from '../api/client'
import JogControls from './JogControls.vue'
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
    name: 'P',
    pen_up_command: 'M3 S0',
    pen_down_command: 'M3 S1000',
    workspace: { x_min: 0, y_min: 0, x_max: 100, y_max: 100 },
  } as MachineProfile
}

function seed(connected: boolean): void {
  const job = useJobStore()
  const { profiles, selectedProfileName } = storeToRefs(job)
  profiles.value = [makeProfile()]
  selectedProfileName.value = 'P'
  usePlotterStore().status.connected = connected
}

function mountJog() {
  return mount(JogControls, { global: { plugins: [i18n] } })
}

describe('JogControls — Repetier-style X/Y/Z', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(client.plotterJog).mockClear()
    vi.mocked(client.plotterHome).mockClear()
  })

  it('jogs Z by the selected step (Z+ / Z−) with dx/dy = 0', async () => {
    seed(true)
    const wrapper = mountJog()
    await nextTick()

    await wrapper.find('[data-test="jog-z-up"]').trigger('click')
    await flushPromises()
    // Default step is 10 mm → dz = +10, dx = dy = 0.
    expect(client.plotterJog).toHaveBeenLastCalledWith(0, 0, 'P', 10)

    await wrapper.find('[data-test="jog-z-down"]').trigger('click')
    await flushPromises()
    expect(client.plotterJog).toHaveBeenLastCalledWith(0, 0, 'P', -10)
  })

  it('jogs X/Y with no Z component', async () => {
    seed(true)
    const wrapper = mountJog()
    await nextTick()

    await wrapper.find('button[aria-label="Jog right (X+)"]').trigger('click')
    await flushPromises()
    expect(client.plotterJog).toHaveBeenLastCalledWith(10, 0, 'P', 0)
  })

  it('homes a single axis, and the centre button homes all', async () => {
    seed(true)
    const wrapper = mountJog()
    await nextTick()

    await wrapper.find('[data-test="home-x"]').trigger('click')
    await flushPromises()
    expect(client.plotterHome).toHaveBeenLastCalledWith('P', 'X')

    await wrapper.find('[data-test="home-z"]').trigger('click')
    await flushPromises()
    expect(client.plotterHome).toHaveBeenLastCalledWith('P', 'Z')

    await wrapper.find('[data-test="home-all"]').trigger('click')
    await flushPromises()
    expect(client.plotterHome).toHaveBeenLastCalledWith('P', undefined)
  })

  it('uses the selected step button for the jog distance', async () => {
    seed(true)
    const wrapper = mountJog()
    await nextTick()

    await wrapper.find('[data-test="step-0.5"]').trigger('click')
    await nextTick()
    await wrapper.find('[data-test="jog-z-up"]').trigger('click')
    await flushPromises()
    expect(client.plotterJog).toHaveBeenLastCalledWith(0, 0, 'P', 0.5)
  })

  it('disables every control when disconnected', async () => {
    seed(false)
    const wrapper = mountJog()
    await nextTick()
    expect(wrapper.find('[data-test="jog-z-up"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('button[aria-label="Jog up (Y+)"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="manual-pen-up"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="home-x"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="step-1"]').attributes('disabled')).toBeDefined()
  })
})
