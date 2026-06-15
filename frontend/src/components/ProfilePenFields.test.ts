// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import ProfilePenFields from './ProfilePenFields.vue'
import type { MachineProfile } from '../api/client'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
})

function makeDraft(over: Partial<MachineProfile> = {}): MachineProfile {
  return {
    name: 'Test',
    units: 'mm',
    workspace: { x_min: 0, y_min: 0, x_max: 300, y_max: 200 },
    origin: 'bottom_left',
    gcode_dialect: 'grbl',
    pen_up_command: 'M3 S0',
    pen_down_command: 'M3 S1000',
    tool_change_method: 'manual_pause',
    tool_change_command: 'M0',
    drawing_speed_mm_s: 50,
    travel_speed_mm_s: 100,
    acceleration_mm_s2: 500,
    pen_lift_time_ms: 0,
    pen_slot_count: 4,
    supports_arcs: false,
    arc_tolerance_mm: 0.1,
    ebb: null,
    pens: null,
    capabilities: null,
    pen_change_position: null,
    ...over,
  } as unknown as MachineProfile
}

function mountFields(draft: MachineProfile) {
  return mount(ProfilePenFields, {
    props: { draft },
    global: { plugins: [i18n] },
  })
}

// Mode card order mirrors the ``modes`` array: manual, host. The retired
// mono / firmware (carousel) modes are no longer offered.
function modeButton(wrapper: ReturnType<typeof mountFields>, index: number) {
  return wrapper.find('[data-test="color-mode-selector"]').findAll('button')[index]!
}

describe('ProfilePenFields mode switching', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('offers exactly two modes (manual + host)', () => {
    const wrapper = mountFields(makeDraft())
    const buttons = wrapper.find('[data-test="color-mode-selector"]').findAll('button')
    expect(buttons.length).toBe(2)
    expect(wrapper.find('[data-test="color-mode-manual"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="color-mode-host"]').exists()).toBe(true)
    // Retired modes are gone from the picker.
    expect(wrapper.find('[data-test="color-mode-mono"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="color-mode-firmware"]').exists()).toBe(false)
  })

  it('host mode gets M0 boundaries and a seeded visual swap plan', async () => {
    const draft = makeDraft({
      tool_change_method: 'manual_pause',
      tool_change_command: 'M0',
    })
    const wrapper = mountFields(draft)
    await modeButton(wrapper, 1).trigger('click') // host
    expect(draft.tool_change_method).toBe('rack')
    expect(draft.tool_change_command).toBe('M0')
    expect(draft.capabilities?.tool_change.mode).toBe('host_macro')
    expect(draft.capabilities?.tool_change.host_swap?.steps.length).toBeGreaterThan(0)
  })

  it('manual mode keeps a single holder (single-holder colour pauses)', async () => {
    // 1 slot + manual_pause is the single-holder manual-swap workflow:
    // the run pauses per COLOUR change.
    const draft = makeDraft({ tool_change_method: 'rack', pen_slot_count: 1 })
    const wrapper = mountFields(draft)
    await modeButton(wrapper, 0).trigger('click') // manual
    expect(draft.tool_change_method).toBe('manual_pause')
    expect(draft.pen_slot_count).toBe(1)
    expect(draft.capabilities?.tool_change.manual_prompt).not.toBeNull()
  })

  it('restores an M0 boundary over a leftover firmware trigger', async () => {
    // A legacy carousel profile carried e.g. ``M6 T{slot}``; selecting a
    // surviving mode must put the pause boundary back to M0 so the run
    // actually pauses on a bare sender.
    const draft = makeDraft({
      tool_change_method: 'carousel',
      tool_change_command: 'M6 T{slot}',
    })
    const wrapper = mountFields(draft)
    await modeButton(wrapper, 0).trigger('click') // manual
    expect(draft.tool_change_method).toBe('manual_pause')
    expect(draft.tool_change_command).toBe('M0')
  })

  it('maps a legacy carousel profile onto the host card', () => {
    // No capabilities block (untouched-since-migration legacy YAML) +
    // carousel method → the host magazine is the closest surviving mode.
    const draft = makeDraft({ tool_change_method: 'carousel', capabilities: null })
    const wrapper = mountFields(draft)
    expect(wrapper.find('[data-test="color-mode-host"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.find('[data-test="color-mode-manual"]').attributes('aria-pressed')).toBe('false')
  })

  it('maps a legacy mono (none) profile onto the manual card', () => {
    const draft = makeDraft({ tool_change_method: 'none', capabilities: null })
    const wrapper = mountFields(draft)
    expect(wrapper.find('[data-test="color-mode-manual"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.find('[data-test="color-mode-host"]').attributes('aria-pressed')).toBe('false')
  })
})
