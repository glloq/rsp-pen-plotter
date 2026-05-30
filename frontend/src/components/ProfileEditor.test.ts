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
    expect(wrapper.find('[data-test="host-macro-editor"]').exists()).toBe(false)
  })

  it('CASE 2 — host mode exposes the macro editor seeded with one line', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    const editor = wrapper.find('[data-test="host-macro-editor"]')
    expect(editor.exists()).toBe(true)
    // setMode seeds a starter line so the profile is immediately valid.
    expect(wrapper.find('[data-test="host-macro-row-0"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="firmware-command"]').exists()).toBe(false)
  })

  it('can add and remove host-macro lines', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    await wrapper.find('[data-test="host-macro-add"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="host-macro-row-1"]').exists()).toBe(true)
    await wrapper.find('[data-test="host-macro-remove-1"]').trigger('click')
    await wrapper.find('[data-test="host-macro-remove-0"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="host-macro-row-0"]').exists()).toBe(false)
  })

  it('blocks Save when a host magazine has no valid command', async () => {
    const wrapper = mountEditor()
    await nextTick()
    await wrapper.find('[data-test="color-mode-host"]').trigger('click')
    await nextTick()
    // Remove the seeded line → empty sequence → invalid.
    await wrapper.find('[data-test="host-macro-remove-0"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="host-macro-empty"]').exists()).toBe(true)
    const saveBtn = wrapper.findAll('button').find((b) => b.text() === 'Save')!
    expect(saveBtn.attributes('disabled')).toBeDefined()
  })
})
