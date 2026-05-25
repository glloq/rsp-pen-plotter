// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import SheetPreview from './SheetPreview.vue'
import { useJobStore } from '../stores/job'
import type { MachineProfile } from '../api/client'

// SheetPreview is mounted by CanvasView with no props or emits. These
// tests pin down the observable surface (toolbar, workspace SVG, the
// "no profile" empty state) as it exists today, so the L10 split into
// ``useSheetGeometry`` + ``<SheetCanvas>`` + ``<PlacementHandles>``
// can be verified against the same DOM contract.

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      sheet: {
        title: 'Sheet',
        zoomIn: 'Zoom in',
        zoomOut: 'Zoom out',
        resetView: 'Reset',
        rotateLeft: 'Rotate left',
        rotateRight: 'Rotate right',
        flipH: 'Flip H',
        flipV: 'Flip V',
        snap: 'Snap',
        snapOff: 'Off',
        placements: 'Placements: {count}',
        outOfBounds: 'Some placements exceed the workspace',
        removePlacement: 'Remove',
        viewHint: 'Wheel = zoom · drag = pan',
      },
      layers: {
        generate: 'Generate',
        generating: 'Generating…',
      },
      preflight: {
        missingPens: 'Missing pens: {slots}',
      },
      upload: {
        pageOf: 'Page {current}/{total}',
      },
      variants: {
        title: 'Variants',
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
    pen_slot_count: 1,
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

function mountSheet() {
  return mount(SheetPreview, {
    global: {
      plugins: [i18n],
    },
  })
}

describe('SheetPreview with no profile', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders nothing when no machine profile is selected', () => {
    // The outer ``v-if="workspace"`` guards every interactive piece —
    // without a selected profile (and therefore no workspace bounds)
    // we don't paint a degenerate empty SVG that would intercept
    // clicks from the surrounding CanvasView layout.
    const wrapper = mountSheet()
    expect(wrapper.find('header').exists()).toBe(false)
  })
})

describe('SheetPreview with a profile seeded', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    seedProfile()
  })

  it('renders the toolbar and the SVG workspace once a profile is selected', async () => {
    const wrapper = mountSheet()
    await nextTick()
    // Header with zoom controls + rotate / flip / snap toolbar.
    expect(wrapper.find('header').exists()).toBe(true)
    // The workspace SVG appears (one rect for the sheet outline plus
    // the grid).
    expect(wrapper.find('svg').exists()).toBe(true)
    // Toolbar shows the zoom percentage rendered next to the +/-
    // buttons; it should read 100% at mount.
    const percentSpan = wrapper.findAll('span').find((s) => /\d+%$/.test(s.text()))
    expect(percentSpan?.text()).toBe('100%')
  })

  it('zoom in / out buttons update the displayed percentage', async () => {
    const wrapper = mountSheet()
    await nextTick()
    const zoomIn = wrapper.find('button[title="Zoom in"]')
    expect(zoomIn.exists()).toBe(true)
    await zoomIn.trigger('click')
    await nextTick()
    // Zoom factor goes ×1.25 per click → 100% → 125%.
    const percentSpan = wrapper.findAll('span').find((s) => /\d+%$/.test(s.text()))
    expect(percentSpan?.text()).toBe('125%')
  })

  it('rotate / flip buttons are disabled when no placement is selected', async () => {
    const wrapper = mountSheet()
    await nextTick()
    // Seeded store has no placements → buttons must be disabled so
    // they can't fire ``store.rotatePlacement(null)`` and crash.
    const rotateLeft = wrapper.find('button[title="Rotate left"]')
    expect(rotateLeft.exists()).toBe(true)
    expect(rotateLeft.attributes('disabled')).toBeDefined()
    const flipH = wrapper.find('button[title="Flip H"]')
    expect(flipH.attributes('disabled')).toBeDefined()
  })

  it('snap select offers off + 1mm / 5mm / 10mm options', async () => {
    const wrapper = mountSheet()
    await nextTick()
    const select = wrapper.find('select')
    expect(select.exists()).toBe(true)
    const optValues = select.findAll('option').map((o) => o.attributes('value'))
    expect(optValues).toEqual(['0', '1', '5', '10'])
  })

  it('Generate button is disabled when no placement carries an svg yet', async () => {
    const wrapper = mountSheet()
    await nextTick()
    const genBtn = wrapper.findAll('button').find((b) => b.text() === 'Generate')
    expect(genBtn).toBeDefined()
    expect(genBtn!.attributes('disabled')).toBeDefined()
  })

  it('renders the workspace outline rect at the profile bounds', async () => {
    const wrapper = mountSheet()
    await nextTick()
    // The first ``<rect>`` inside the SVG is the white sheet outline
    // — its width/height should match the profile workspace.
    const rect = wrapper.find('svg rect')
    expect(rect.attributes('width')).toBe('297')
    expect(rect.attributes('height')).toBe('420')
  })
})
