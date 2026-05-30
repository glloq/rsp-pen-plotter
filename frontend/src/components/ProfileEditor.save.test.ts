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

  it('saves a host magazine profile with its visual swap steps', async () => {
    const wrapper = mountSeeded()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    await clickSave(wrapper)
    expect(saved).toHaveLength(1)
    expect(saved[0]!.capabilities?.tool_change.mode).toBe('host_macro')
    expect(saved[0]!.capabilities?.tool_change.host_swap?.steps.length).toBeGreaterThan(0)
  })

  it('persists per-slot positions and Z heights from the host editor', async () => {
    const wrapper = mountSeeded()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    const x0 = wrapper.find('[data-test="host-pos-x-0"]')
    const y0 = wrapper.find('[data-test="host-pos-y-0"]')
    await x0.setValue('12.5')
    await x0.trigger('change')
    await y0.setValue('200')
    await y0.trigger('change')
    const safe = wrapper.find('[data-test="host-safe-z"]')
    await safe.setValue('5')
    await safe.trigger('change')
    await nextTick()
    await clickSave(wrapper)
    const profile = saved.at(-1)!
    expect(profile.pens?.find((p) => p.index === 0)?.position).toEqual({ x: 12.5, y: 200 })
    expect(profile.capabilities?.tool_change.host_swap?.safe_z_mm).toBe(5)
  })

  it('persists the dedicated magazine servo head-height commands', async () => {
    const wrapper = mountSeeded()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    const up = wrapper.find('[data-test="host-head-up"]')
    const down = wrapper.find('[data-test="host-head-down"]')
    await up.setValue('M280 P0 S10')
    await up.trigger('change')
    await down.setValue('M280 P0 S70')
    await down.trigger('change')
    await nextTick()
    await clickSave(wrapper)
    const swap = saved.at(-1)!.capabilities?.tool_change.host_swap
    expect(swap?.head_up_command).toBe('M280 P0 S10')
    expect(swap?.head_down_command).toBe('M280 P0 S70')
  })

  it('persists the slot clearance vector and seeds advance/retract steps', async () => {
    const wrapper = mountSeeded()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    await wrapper.find('[data-test="host-clearance-axis"]').setValue('x')
    await wrapper.find('[data-test="host-clearance-dir"]').setValue('-')
    const mm = wrapper.find('[data-test="host-clearance-mm"]')
    await mm.setValue('15')
    await mm.trigger('change')
    await nextTick()
    await clickSave(wrapper)
    const swap = saved.at(-1)!.capabilities?.tool_change.host_swap
    expect(swap?.clearance_axis).toBe('x')
    expect(swap?.clearance_dir).toBe('-')
    expect(swap?.clearance_mm).toBe(15)
    // The default sequence is crash-safe: it includes advance + retract.
    const kinds = swap?.steps.map((s) => s.kind) ?? []
    expect(kinds).toContain('advance_to_slot')
    expect(kinds).toContain('retract_from_slot')
  })
})
