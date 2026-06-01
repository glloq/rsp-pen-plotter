// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import AppFooter from './AppFooter.vue'
import { useJobStore, type Placement } from '../stores/job'
import type { MachineProfile, PreflightReport } from '../api/client'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      footer: {
        size: 'Size',
        scale: 'Scale',
        estimate: 'Est.',
        estimatePending: '— generate to estimate',
        estimatePendingHint: 'Generate the G-code for a realistic estimate.',
        penChanges: 'Pen changes',
      },
      sheet: { outOfBounds: 'Out of bounds' },
      preflight: { missingPens: 'Install pen {slots}' },
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
    pen_slot_count: 1,
    supports_arcs: false,
    arc_tolerance_mm: 0.1,
    ebb: null,
    pens: null,
  }
}

// A minimal placement with a single layer, sized 150×100 mm on the plan
// from a 300×200 mm source bbox → a 50 % scale.
function makePlacement(overrides: Partial<Placement> = {}): Placement {
  return {
    id: 'p1',
    library_file_id: 'lib1',
    source_file: 'art.png',
    source_mime: 'image/png',
    job_id: 'lib1',
    rerenderable: true,
    svg: '<svg></svg>',
    layers: [{ layer_id: 'l1', target_pen_slot: null, total_length_mm: 1000 }],
    source_bbox: { x_min: 0, y_min: 0, x_max: 300, y_max: 200 },
    layer_algorithms: {},
    upload_warnings: [],
    upload_metadata: {},
    last_file: null,
    last_options: undefined,
    visibility: {},
    x_mm: 10,
    y_mm: 10,
    width_mm: 150,
    height_mm: 100,
    rotation: 0,
    flip_h: false,
    flip_v: false,
    variants: [],
    active_variant_id: '',
    ...overrides,
  } as unknown as Placement
}

function seed(placement: Placement, preflight: PreflightReport | null = null): void {
  const job = useJobStore()
  const refs = storeToRefs(job)
  refs.profiles.value = [makeProfile()]
  refs.selectedProfileName.value = 'Test A3'
  refs.placements.value = [placement]
  refs.selectedPlacementId.value = placement.id
  refs.preflight.value = preflight
}

function makePreflight(seconds: number): PreflightReport {
  return {
    ok: true,
    within_bounds: true,
    width_mm: 150,
    height_mm: 100,
    scale: 0.5,
    drawing_length_mm: 1000,
    travel_length_mm: 200,
    estimated_seconds: seconds,
    pen_changes: 3,
    layer_count: 1,
    path_count: 10,
    missing_pen_slots: [],
    warnings: [],
  }
}

function mountFooter() {
  return mount(AppFooter, { global: { plugins: [i18n] } })
}

describe('AppFooter', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('shows the placed footprint size, not a re-fit of the source', async () => {
    seed(makePlacement())
    const wrapper = mountFooter()
    await nextTick()
    expect(wrapper.text()).toContain('150×100 mm')
  })

  it('shows the scale relative to the source natural size', async () => {
    seed(makePlacement())
    const wrapper = mountFooter()
    await nextTick()
    // 150 mm placed / 300 mm natural = 50 %.
    expect(wrapper.text()).toContain('50%')
  })

  it('accounts for 90° rotation when computing scale', async () => {
    // Rotated a quarter turn: the 100 mm placed width now maps onto the
    // source's 200 mm height → 50 %.
    seed(makePlacement({ rotation: 90, width_mm: 100, height_mm: 150 }))
    const wrapper = mountFooter()
    await nextTick()
    expect(wrapper.text()).toContain('50%')
  })

  it('shows a pending placeholder for the estimate until preflight has run', async () => {
    seed(makePlacement(), null)
    const wrapper = mountFooter()
    await nextTick()
    expect(wrapper.find('[data-test="footer-estimate-pending"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('— generate to estimate')
  })

  it('shows the realistic preflight estimate once the gcode has been computed', async () => {
    seed(makePlacement(), null)
    const wrapper = mountFooter()
    await nextTick()
    // Setting the preflight report AFTER the seed watchers have flushed
    // mirrors the real flow: /preflight resolves and populates the
    // report once the plan is stable (changing the profile clears it).
    const job = useJobStore()
    storeToRefs(job).preflight.value = makePreflight(125)
    await nextTick()
    expect(wrapper.find('[data-test="footer-estimate-pending"]').exists()).toBe(false)
    // 125 s → 2m 05s.
    expect(wrapper.text()).toContain('2m 05s')
    // Pen changes come from the same preflight report.
    expect(wrapper.text()).toContain('Pen changes')
    expect(wrapper.text()).toContain('3')
  })

  it('renders nothing when there is no drawing on the plan', () => {
    const job = useJobStore()
    const refs = storeToRefs(job)
    refs.profiles.value = [makeProfile()]
    refs.selectedProfileName.value = 'Test A3'
    const wrapper = mountFooter()
    expect(wrapper.find('footer').exists()).toBe(false)
  })
})
