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

// Mode card order mirrors the ``modes`` array: mono, manual, firmware, host.
function modeButton(wrapper: ReturnType<typeof mountFields>, index: number) {
  return wrapper.find('[data-test="color-mode-selector"]').findAll('button')[index]!
}

describe('ProfilePenFields mode switching', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('seeds the firmware trigger when switching manual → firmware', async () => {
    // A leftover ``M0`` sent as a firmware trigger feed-holds the
    // controller with no operator prompt.
    const draft = makeDraft()
    const wrapper = mountFields(draft)
    await modeButton(wrapper, 2).trigger('click') // firmware
    expect(draft.tool_change_method).toBe('carousel')
    expect(draft.tool_change_command).toBe('M6 T{slot}')
    expect(draft.capabilities?.tool_change.mode).toBe('firmware')
  })

  it('restores M0 when switching firmware → manual', async () => {
    const draft = makeDraft({
      tool_change_method: 'carousel',
      tool_change_command: 'T{slot}',
    })
    const wrapper = mountFields(draft)
    await modeButton(wrapper, 1).trigger('click') // manual
    expect(draft.tool_change_method).toBe('manual_pause')
    expect(draft.tool_change_command).toBe('M0')
    expect(draft.capabilities?.tool_change.mode).toBe('manual')
    expect(draft.capabilities?.tool_change.manual_prompt).not.toBeNull()
  })

  it('keeps a custom firmware trigger when re-entering firmware mode', async () => {
    const draft = makeDraft({ tool_change_command: 'T{slot} G4 P500' })
    const wrapper = mountFields(draft)
    await modeButton(wrapper, 2).trigger('click') // firmware
    expect(draft.tool_change_command).toBe('T{slot} G4 P500')
  })

  it('host mode gets M0 boundaries and a seeded visual swap plan', async () => {
    const draft = makeDraft({
      tool_change_method: 'carousel',
      tool_change_command: 'M6 T{slot}',
    })
    const wrapper = mountFields(draft)
    await modeButton(wrapper, 3).trigger('click') // host
    expect(draft.tool_change_method).toBe('rack')
    expect(draft.tool_change_command).toBe('M0')
    expect(draft.capabilities?.tool_change.mode).toBe('host_macro')
    expect(draft.capabilities?.tool_change.host_swap?.steps.length).toBeGreaterThan(0)
  })

  it('manual mode keeps a single holder (AxiDraw-style colour pauses)', async () => {
    // 1 slot + manual_pause is the mono manual-swap workflow: the run
    // pauses per COLOUR change. The mode switch used to force the count
    // to 2, silently flipping the pause semantics to slot-based.
    const draft = makeDraft({ tool_change_method: 'none', pen_slot_count: 1 })
    const wrapper = mountFields(draft)
    await modeButton(wrapper, 1).trigger('click') // manual
    expect(draft.tool_change_method).toBe('manual_pause')
    expect(draft.pen_slot_count).toBe(1)
  })

  it('mono mode drops to one slot and M0', async () => {
    const draft = makeDraft({ tool_change_command: 'M6 T{slot}' })
    const wrapper = mountFields(draft)
    await modeButton(wrapper, 0).trigger('click') // mono
    expect(draft.tool_change_method).toBe('none')
    expect(draft.pen_slot_count).toBe(1)
    expect(draft.tool_change_command).toBe('M0')
  })
})
