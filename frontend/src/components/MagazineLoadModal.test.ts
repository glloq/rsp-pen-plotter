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
    saveProfile: vi.fn(async (p: unknown) => p),
    getProfiles: vi.fn(async () => []),
  }
})

import * as client from '../api/client'
import MagazineLoadModal from './MagazineLoadModal.vue'
import { ensureMagazineLoaded } from '../composables/magazineGate'
import { useJobStore, type Placement } from '../stores/job'
import type { LayerInfo, MachineProfile, PenSlot } from '../api/client'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      magazinePlan: {
        launchTitle: 'Load the magazine',
        launchIntro: 'Mount these colours.',
        slotLabel: 'Slot',
        slotPick: 'Slot for {name}',
        swapsTitle: 'Mid-print swaps ({count}):',
        pauseNote: 'Pauses will name the ink.',
        noPauseSupport: 'No tool-change support.',
        launchConfirm: 'Loaded — start the print',
        launchPreparing: 'Preparing…',
        launchCancel: 'Cancel',
        launchRegenFailed: 'Regen failed',
        applyFailed: 'Apply failed',
      },
    },
  },
})

function pen(index: number, color: string): PenSlot {
  return {
    index,
    name: `Pen ${index}`,
    color,
    installed: true,
    position: null,
    pen_up_command: null,
    pen_down_command: null,
  }
}

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
    pens: [pen(0, '#000000'), pen(1, '#ff0000')],
  } as MachineProfile
}

function makeLayer(id: string, hex: string, order: number): LayerInfo {
  return {
    layer_id: id,
    source_color: hex,
    assigned_color_hex: hex,
    color_assignment: 'manual',
    color_label: null,
    target_pen_slot: null,
    drawing_speed_mm_s: null,
    simplify_tolerance_mm: 0.05,
    optimize: true,
    pause_before: 'auto',
    path_count: 1,
    total_length_mm: 10,
    draw_order: order,
  } as LayerInfo
}

function makePlacement(layers: LayerInfo[]): Placement {
  return {
    id: 'p1',
    library_file_id: null,
    source_file: 'x.png',
    source_mime: 'image/png',
    job_id: null,
    rerenderable: false,
    svg: '<svg/>',
    layers,
    source_bbox: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 },
    layer_algorithms: {},
    upload_warnings: [],
    upload_metadata: {},
    last_file: null,
    last_options: undefined,
    visibility: {},
    rotation: 0,
    flip_h: false,
    flip_v: false,
    x_mm: 0,
    y_mm: 0,
    width_mm: 10,
    height_mm: 10,
  } as Placement
}

async function seed(): Promise<ReturnType<typeof useJobStore>> {
  const job = useJobStore()
  const { profiles, selectedProfileName } = storeToRefs(job)
  const profile = makeProfile()
  profiles.value = [profile]
  selectedProfileName.value = profile.name
  job.placements = [
    makePlacement([
      makeLayer('a', '#111111', 0),
      makeLayer('b', '#222222', 1),
      makeLayer('c', '#333333', 2),
    ]),
  ]
  job.selectedPlacementId = 'p1'
  job.gcode = 'G1 X0'
  // The modal regenerates after applying the plan; stub the heavy
  // pipeline with a gcode refresh.
  job.generate = vi.fn(async () => {
    job.gcode = 'G1 X1'
  }) as never
  await nextTick()
  return job
}

function mountModal() {
  return mount(MagazineLoadModal, { global: { plugins: [i18n] } })
}

describe('MagazineLoadModal', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(client.saveProfile).mockClear()
  })

  it('opens via the gate and lists the initial loading with slot selects', async () => {
    await seed()
    const wrapper = mountModal()
    const gate = ensureMagazineLoaded()
    await nextTick()
    expect(wrapper.find('[data-test="magazine-load-modal"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="magazine-load-slot-0"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="magazine-load-swaps"]').text()).toContain('#333333')
    await wrapper.find('[data-test="magazine-load-cancel"]').trigger('click')
    await expect(gate).resolves.toBe('cancelled')
  })

  it('skips the gate for single-ink jobs', async () => {
    const job = await seed()
    job.placements[0]!.layers = [makeLayer('a', '#111111', 0)]
    await expect(ensureMagazineLoaded()).resolves.toBe('skipped')
  })

  it('opens for a single-holder machine with a manual-swap plan', async () => {
    const job = await seed()
    // Single holder (mono-pen): one initial load + a manual swap at each
    // colour change. The gate no longer skips these.
    job.profiles[0]!.pen_slot_count = 1
    job.profiles[0]!.pens = [pen(0, '#000000')]
    const wrapper = mountModal()
    const gate = ensureMagazineLoaded()
    await nextTick()
    expect(wrapper.find('[data-test="magazine-load-modal"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="magazine-load-slot-0"]').exists()).toBe(true)
    // Inks b/c (3 inks, 1 slot) become mid-print manual swaps.
    const swaps = wrapper.find('[data-test="magazine-load-swaps"]').text()
    expect(swaps).toContain('#222222')
    expect(swaps).toContain('#333333')
    await wrapper.find('[data-test="magazine-load-cancel"]').trigger('click')
    await expect(gate).resolves.toBe('cancelled')
  })

  it('confirms: applies the (remapped) plan, regenerates, resolves confirmed', async () => {
    const job = await seed()
    const wrapper = mountModal()
    const gate = ensureMagazineLoaded()
    await nextTick()

    // Remap: ink of plan slot 0 (#111111) goes to physical slot 1 —
    // the colliding row (#222222, plan slot 1) swaps back to slot 0.
    await wrapper.find('[data-test="magazine-load-slot-0"]').setValue('1')
    await wrapper.find('[data-test="magazine-load-confirm"]').trigger('click')
    await expect(gate).resolves.toBe('confirmed')

    const layers = job.placements[0]!.layers
    // Plan slots a:0 b:1 c:0 → permuted a:1 b:0 c:1.
    expect(layers.map((l) => l.target_pen_slot)).toEqual([1, 0, 1])

    const saved = vi.mocked(client.saveProfile).mock.calls[0]![0] as MachineProfile
    expect((saved.pens ?? []).map((p) => p.color)).toEqual(['#222222', '#111111'])

    // Regenerated after the mutation invalidated the old program.
    expect(job.generate).toHaveBeenCalledTimes(1)
    expect(job.gcode).toBe('G1 X1')
  })
})
