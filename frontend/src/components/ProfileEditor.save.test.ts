// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import ProfileEditor from './ProfileEditor.vue'
import { useJobStore } from '../stores/job'
import type { MachineProfile } from '../api/client'

// Regression for "Impossible d'enregistrer le profil": changing the
// pen-slot count (e.g. switching to the Mono card → 1) re-ran
// ``normalizePens`` on the *reactive* draft, which re-inserted reactive
// pen proxies into ``pens``. ``structuredClone`` then threw a
// DataCloneError inside ``save()``, surfacing as the generic save-failed
// toast. The draft now serialises via a JSON deep-clone, so save fires.

const saved: MachineProfile[] = []
vi.mock('../api/client', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>
  return {
    ...actual,
    saveProfile: vi.fn(async (p: MachineProfile) => {
      // Mirror the wire: must be plain-cloneable JSON.
      saved.push(JSON.parse(JSON.stringify(p)))
      return p
    }),
    getProfiles: vi.fn(async () => []),
  }
})

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
})

function makeProfile(): MachineProfile {
  return {
    name: 'T',
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
    pen_slot_count: 2,
    supports_arcs: false,
    arc_tolerance_mm: 0.1,
    ebb: null,
    pens: null,
  }
}

function mountSeeded() {
  setActivePinia(createPinia())
  const job = useJobStore()
  const { profiles, selectedProfileName } = storeToRefs(job)
  profiles.value = [makeProfile()]
  selectedProfileName.value = 'T'
  return mount(ProfileEditor, { global: { plugins: [i18n] } })
}

async function clickSave(wrapper: ReturnType<typeof mountSeeded>) {
  const btn = wrapper.findAll('button').find((b) => b.text().trim() === 'profile.save')!
  await btn.trigger('click')
  await nextTick()
  await new Promise((r) => setTimeout(r, 20))
}

describe('ProfileEditor save serialisation', () => {
  beforeEach(() => {
    saved.length = 0
  })

  it('saves after switching to Mono (pen count → 1)', async () => {
    const wrapper = mountSeeded()
    await nextTick()
    await wrapper.find('[data-test="color-mode-mono"]').trigger('click')
    await nextTick()
    await clickSave(wrapper)
    expect(saved).toHaveLength(1)
    expect(saved[0]!.pen_slot_count).toBe(1)
  })

  it('saves after raising the pen count (proxy reuse path)', async () => {
    const wrapper = mountSeeded()
    await nextTick()
    // Firmware magazine keeps multiple pens; bump the count so the
    // watcher re-runs normalizePens and retains existing slots.
    await wrapper.find('[data-test="color-mode-firmware"]').trigger('click')
    await nextTick()
    const countInput = wrapper.find('[data-test="magazine-pen-count"] input')
    await countInput.setValue('4')
    await countInput.trigger('change')
    await nextTick()
    await clickSave(wrapper)
    expect(saved).toHaveLength(1)
    expect(saved[0]!.pens?.length).toBe(4)
  })

  it('saves a host-macro profile end to end', async () => {
    const wrapper = mountSeeded()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    await clickSave(wrapper)
    expect(saved).toHaveLength(1)
    expect(saved[0]!.capabilities?.tool_change.mode).toBe('host_macro')
    expect(saved[0]!.capabilities?.tool_change.host_macro.length).toBeGreaterThan(0)
  })
})
