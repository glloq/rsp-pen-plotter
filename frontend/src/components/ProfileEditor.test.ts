// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import ProfileEditor from './ProfileEditor.vue'
import { useJobStore } from '../stores/job'
import type { MachineProfile } from '../api/client'

// ProfileEditor is mounted by PlotterDrawer with no props or emits.
// These tests pin down the observable surface (profile picker, the
// five collapsible fieldsets, the action buttons) so the L10 split
// into ``useProfileDraft`` + ``<ProfilePenFields>`` can be verified
// against the same DOM contract.

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      profile: {
        newProfile: '+ New',
        newProfileDefault: 'New profile',
        sectionIdentity: 'Identity',
        sectionWorkspace: 'Workspace',
        motion: 'Motion',
        pen: 'Pen',
        advanced: 'Advanced',
        advancedHint: 'EBB / arcs',
        save: 'Save',
        delete: 'Delete',
        duplicate: 'Duplicate',
        download: 'Download',
        units: 'Units',
        origin: 'Origin',
        originTopLeft: 'Top-left',
        originBottomLeft: 'Bottom-left',
        originCenter: 'Centre',
        originHint: '',
        workspaceHint: '',
        drawingSpeed: 'Drawing speed',
        travelSpeed: 'Travel speed',
        drawingSpeedHint: '',
        travelSpeedHint: '',
        acceleration: 'Acceleration',
        accelerationHint: '',
        penUp: 'Pen up',
        penDown: 'Pen down',
        penUpHint: '',
        penDownHint: '',
        toolChangeMethod: 'Tool change',
        toolChangeMethodHint: '',
        toolChangeCommand: 'Tool change cmd',
        penSlots: 'Pen slots',
        penSlotsHint: '',
        magazine: 'Magazine',
        installed: 'Installed',
        pickupPosition: 'Pickup',
        penUpOverride: 'Up override',
        penDownOverride: 'Down override',
        tcManualPause: 'Manual',
        tcCarousel: 'Carousel',
        tcRack: 'Rack',
        tcNone: 'None',
        gcodeDialect: 'Dialect',
        name: 'Name',
        supportsArcs: 'Supports arcs',
        arcTolerance: 'Arc tolerance',
        ebbStepsPerMm: 'Steps/mm',
        ebbServoUp: 'Servo up',
        ebbServoDown: 'Servo down',
        ebbServoRate: 'Servo rate',
        ebbSerialTerminator: 'Terminator',
        saveFailed: 'Save failed',
        deleteFailed: 'Delete failed',
        unsavedHint: 'unsaved',
        preset: 'Preset',
        presetNone: 'None',
      },
      confirm: {
        deleteProfileTitle: 'Delete?',
        deleteProfileMsg: 'Delete {name}?',
        cancel: 'Cancel',
      },
    },
  },
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
    pen_slot_count: 2,
    supports_arcs: false,
    arc_tolerance_mm: 0.1,
    ebb: null,
    pens: null,
  }
}

function seedProfile(): void {
  const job = useJobStore()
  const { profiles, selectedProfileName } = storeToRefs(job)
  const profile = makeProfile()
  profiles.value = [profile]
  selectedProfileName.value = profile.name
}

function mountEditor() {
  return mount(ProfileEditor, {
    global: {
      plugins: [i18n],
    },
  })
}

describe('ProfileEditor with no profile selected', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('does not render the draft form before a profile syncs', () => {
    // Fresh store: selectedProfile is null → syncDraft sets draft.value
    // to null → the inner v-if guards every fieldset.
    const wrapper = mountEditor()
    // Section headings only appear once a draft exists.
    expect(wrapper.text()).not.toContain('Workspace')
  })
})

describe('ProfileEditor with a profile seeded', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    seedProfile()
  })

  it('clones the selected profile into the draft and renders the fieldsets', async () => {
    const wrapper = mountEditor()
    await nextTick()
    // All five fieldset headings should appear (Identity, Workspace,
    // Motion, Pen, Advanced — each in a ``<details>``).
    const text = wrapper.text()
    expect(text).toContain('Workspace')
    expect(text).toContain('Motion')
    expect(text).toContain('Pen')
    expect(text).toContain('Advanced')
  })

  it('binds the workspace dimensions inputs to the draft', async () => {
    const wrapper = mountEditor()
    await nextTick()
    // X max should reflect the seeded profile's 297mm.
    const inputs = wrapper.findAll('input[type="number"]')
    const xmax = inputs.find((i) => (i.element as HTMLInputElement).valueAsNumber === 297)
    expect(xmax).toBeDefined()
  })

  it('renders the four tool-change mode cards with the seeded mode active', async () => {
    // Per-pen colour cards now live in the Colours tab; the profile tab
    // exposes the tool-change mode (mono / manual / firmware / host) and,
    // for multicolour modes, the pen count. The seeded profile uses
    // manual_pause → the "manual" card is active.
    const wrapper = mountEditor()
    await nextTick()
    expect(wrapper.find('[data-test="color-mode-mono"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="color-mode-manual"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="color-mode-firmware"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="color-mode-host"]').exists()).toBe(true)
    const manual = wrapper.find('[data-test="color-mode-manual"]')
    expect(manual.attributes('aria-pressed')).toBe('true')
  })

  it('shows the pen count for a multicolour profile', async () => {
    // pen_slot_count = 2 with a non-mono mode → the magazine pen-count
    // input is visible and reflects the seeded value.
    const wrapper = mountEditor()
    await nextTick()
    const block = wrapper.find('[data-test="magazine-pen-count"]')
    expect(block.exists()).toBe(true)
    const input = block.find('input[type="number"]')
    expect((input.element as HTMLInputElement).valueAsNumber).toBe(2)
  })

  it('shows the Save button enabled when a draft exists', async () => {
    const wrapper = mountEditor()
    await nextTick()
    const saveBtn = wrapper.findAll('button').find((b) => b.text() === 'Save')
    expect(saveBtn).toBeDefined()
    expect(saveBtn!.attributes('disabled')).toBeUndefined()
  })

  it('hides the acceleration-not-on-wire warning for a GRBL profile', async () => {
    const wrapper = mountEditor()
    await nextTick()
    expect(wrapper.find('[data-test="accel-not-on-wire"]').exists()).toBe(false)
  })

  it('warns that acceleration is not sent on the wire for an EBB profile', async () => {
    const wrapper = mountEditor()
    await nextTick()
    const dialect = wrapper
      .findAll('select')
      .find((s) => s.findAll('option').some((o) => o.attributes('value') === 'ebb'))!
    await dialect.setValue('ebb')
    await nextTick()
    expect(wrapper.find('[data-test="accel-not-on-wire"]').exists()).toBe(true)
  })

  it('flags an inverted workspace and disables Save', async () => {
    const wrapper = mountEditor()
    await nextTick()
    // Drive X max below X min → degenerate rectangle.
    const inputs = wrapper.findAll('input[type="number"]')
    const xmax = inputs.find((i) => (i.element as HTMLInputElement).valueAsNumber === 297)!
    await xmax.setValue('-5')
    await nextTick()
    expect(wrapper.find('[data-test="workspace-invalid"]').exists()).toBe(true)
    const saveBtn = wrapper.findAll('button').find((b) => b.text() === 'Save')!
    expect(saveBtn.attributes('disabled')).toBeDefined()
  })

  it('no longer offers the removed "center" origin option', async () => {
    const wrapper = mountEditor()
    await nextTick()
    const originValues = wrapper.findAll('option').map((o) => o.attributes('value'))
    expect(originValues).not.toContain('center')
  })

  it('CASE 1 — firmware mode exposes the single tool-change command field', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-firmware"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="firmware-command"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="host-swap-editor"]').exists()).toBe(false)
  })

  it('CASE 2 — host mode exposes the visual swap builder seeded with steps', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="host-swap-editor"]').exists()).toBe(true)
    // setMode seeds a sensible default sequence so it's immediately valid.
    expect(wrapper.find('[data-test="host-step-0"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="firmware-command"]').exists()).toBe(false)
  })

  it('can add and remove host swap steps', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    // Default seeds a crash-safe sequence of 10 steps (indices 0..9).
    expect(wrapper.find('[data-test="host-step-9"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="host-step-10"]').exists()).toBe(false)
    await wrapper.find('[data-test="host-step-add"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="host-step-10"]').exists()).toBe(true)
    await wrapper.find('[data-test="host-step-remove-10"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="host-step-10"]').exists()).toBe(false)
  })

  it('blocks Save when a grab step has no take command', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    const saveBtn = () => wrapper.findAll('button').find((b) => b.text() === 'Save')!
    // Default is valid (grab/release commands seeded) → Save enabled.
    expect(saveBtn().attributes('disabled')).toBeUndefined()
    // Clear the take command while a grab step exists → invalid.
    await wrapper.find('[data-test="host-grab-command"]').setValue('')
    await nextTick()
    expect(saveBtn().attributes('disabled')).toBeDefined()
  })

  it('host mode offers the ① magazine + ② action card selectors', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    // ① magazine type.
    expect(wrapper.find('[data-test="host-mechanism-rack"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="host-mechanism-dock"]').exists()).toBe(true)
    // ② action type — shown for both mechanisms now.
    expect(wrapper.find('[data-test="host-action"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="host-action-command"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="host-action-motion"]').exists()).toBe(true)
    // Default rack action is 'command' → latch command fields present.
    expect(wrapper.find('[data-test="host-grab-command"]').exists()).toBe(true)
  })

  it('a motion action hides the latch commands and keeps Save valid', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    // Switch the ② action to motion (friction / magnetic hold).
    await wrapper.find('[data-test="host-action-motion"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="host-grab-command"]').exists()).toBe(false)
    // A motion grab needs no command → Save stays enabled despite the
    // grab/release steps in the sequence.
    const saveBtn = () => wrapper.findAll('button').find((b) => b.text() === 'Save')!
    expect(saveBtn().attributes('disabled')).toBeUndefined()
    // Back to 'command' reveals the latch command fields again.
    await wrapper.find('[data-test="host-action-command"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="host-grab-command"]').exists()).toBe(true)
  })

  it('switching to a dock defaults the action to motion (magnetic / kinematic)', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    await wrapper.find('[data-test="host-mechanism-dock"]').trigger('click')
    await nextTick()
    // Dock preset selects the motion action → latch commands hidden.
    expect(wrapper.find('[data-test="host-action-motion"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.find('[data-test="host-grab-command"]').exists()).toBe(false)
  })

  it('shows a per-slot position table and Z height fields in the host editor', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="host-positions"]').exists()).toBe(true)
    // The seeded profile has 2 slots → rows 0 and 1.
    expect(wrapper.find('[data-test="host-pos-row-0"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="host-pos-row-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="host-heights"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="host-safe-z"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="host-engage-z"]').exists()).toBe(true)
  })

  it('flags uncalibrated installed slots in the host positions table', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    // Seeded 2-slot magazine with no positions → both rows flagged + summary.
    expect(wrapper.find('[data-test="host-uncalibrated"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="host-pos-cal-0"]').text()).toBe('⚠')
    // Calibrate both slots → the row turns ✓ and the summary clears.
    for (const i of [0, 1]) {
      const x = wrapper.find(`[data-test="host-pos-x-${i}"]`)
      await x.setValue('10')
      await x.trigger('change')
    }
    await nextTick()
    expect(wrapper.find('[data-test="host-pos-cal-0"]').text()).toBe('✓')
    expect(wrapper.find('[data-test="host-uncalibrated"]').exists()).toBe(false)
  })

  it('groups the head-height fields under a collapsible block', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    const group = wrapper.find('[data-test="host-heights-group"]')
    expect(group.exists()).toBe(true)
    expect(group.element.tagName.toLowerCase()).toBe('details')
    // Both the servo and the Z fields live inside the group.
    expect(group.find('[data-test="host-head-up"]').exists()).toBe(true)
    expect(group.find('[data-test="host-safe-z"]').exists()).toBe(true)
  })

  it('reset sequence restores the mechanism preset', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    // Rack preset seeds 10 steps (indices 0..9).
    expect(wrapper.find('[data-test="host-step-9"]').exists()).toBe(true)
    await wrapper.find('[data-test="host-step-remove-9"]').trigger('click')
    await wrapper.find('[data-test="host-step-remove-8"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="host-step-8"]').exists()).toBe(false)
    // Reset → the full preset is back.
    await wrapper.find('[data-test="host-step-reset"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="host-step-9"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="host-step-10"]').exists()).toBe(false)
  })

  it('previews the compiled sequence and resolves coordinates once calibrated', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    const preview = wrapper.find('[data-test="host-preview"]')
    expect(preview.exists()).toBe(true)
    expect(preview.find('[data-test="host-preview-line-0"]').exists()).toBe(true)
    // Calibrate both example slots → a move line resolves to real coords.
    for (const [i, x, y] of [
      [0, '10', '200'],
      [1, '40', '200'],
    ] as const) {
      await wrapper.find(`[data-test="host-pos-x-${i}"]`).setValue(x)
      await wrapper.find(`[data-test="host-pos-x-${i}"]`).trigger('change')
      await wrapper.find(`[data-test="host-pos-y-${i}"]`).setValue(y)
      await wrapper.find(`[data-test="host-pos-y-${i}"]`).trigger('change')
    }
    await nextTick()
    expect(preview.text()).toContain('X10 Y200')
  })

  it('shows magazine servo head-height fields, disabled once a Z axis is set', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    const up = wrapper.find('[data-test="host-head-up"]')
    expect(up.exists()).toBe(true)
    // Servo mode by default → editable.
    expect(up.attributes('disabled')).toBeUndefined()
    // Configure a Z axis → servo command greyed out (ignored).
    const safe = wrapper.find('[data-test="host-safe-z"]')
    await safe.setValue('5')
    await safe.trigger('change')
    await nextTick()
    expect(wrapper.find('[data-test="host-head-up"]').attributes('disabled')).toBeDefined()
  })

  it('warns (without blocking) when the engage depth sits above the safe height', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    const safe = wrapper.find('[data-test="host-safe-z"]')
    const engage = wrapper.find('[data-test="host-engage-z"]')
    await safe.setValue('5')
    await safe.trigger('change')
    await engage.setValue('-2')
    await engage.trigger('change')
    await nextTick()
    expect(wrapper.find('[data-test="host-z-warning"]').exists()).toBe(false)
    // Engage shallower than safe → non-blocking warning, Save still enabled.
    await engage.setValue('8')
    await engage.trigger('change')
    await nextTick()
    expect(wrapper.find('[data-test="host-z-warning"]').exists()).toBe(true)
    const saveBtn = wrapper.findAll('button').find((b) => b.text() === 'Save')!
    expect(saveBtn.attributes('disabled')).toBeUndefined()
  })
})
