// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

vi.mock('../api/client', async (orig) => {
  const actual = await orig<typeof import('../api/client')>()
  return {
    ...actual,
    enqueuePrint: vi.fn(async () => undefined),
    listQueue: vi.fn(async () => []),
    plotterRun: vi.fn(async () => ({
      connected: true,
      total: 0,
      sent: 0,
      acked: 0,
      state: 'idle' as const,
      message: null,
    })),
  }
})

import en from '../locales/en.json'
import * as client from '../api/client'
import PrintQueuePanel from './PrintQueuePanel.vue'
import { useMagazineGateState } from '../composables/magazineGate'
import { useJobStore, type Placement } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'
import type { LayerInfo, MachineProfile, PenSlot } from '../api/client'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en },
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
    // Manual swap — the operator's reported scenario: no physical magazine.
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
    source_file: 'art.png',
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

// Seed a MULTI-INK job on a 2-slot profile: under the old behaviour this
// is exactly the shape that made enqueue pop the magazine-load modal.
async function seedMultiInkJob(): Promise<ReturnType<typeof useJobStore>> {
  const job = useJobStore()
  const { profiles, selectedProfileName } = storeToRefs(job)
  const profile = makeProfile()
  profiles.value = [profile]
  selectedProfileName.value = profile.name
  job.placements = [makePlacement([makeLayer('a', '#111111', 0), makeLayer('b', '#222222', 1)])]
  job.selectedPlacementId = 'p1'
  // The store invalidates cached outputs (incl. gcode) on a nextTick
  // watcher when the profile / scene changes — set the gcode AFTER that
  // has fired so it survives into the mount.
  await nextTick()
  job.gcode = 'G1 X0\nG1 X1'
  await nextTick()
  return job
}

describe('PrintQueuePanel — enqueue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(client.enqueuePrint).mockClear()
    // The gate is a module-level singleton; clear any leak between tests.
    useMagazineGateState().open = false
  })

  it('queues the current G-code directly, without opening the magazine modal', async () => {
    const job = await seedMultiInkJob()
    // Disconnected → the single "Add current G-code" button renders, which
    // is the exact control the operator reported.
    expect(usePlotterStore().status.connected).toBe(false)

    const wrapper = mount(PrintQueuePanel, { global: { plugins: [i18n] } })
    const addBtn = wrapper.find('[data-test="queue-enqueue"]')
    expect(addBtn.exists()).toBe(true)

    await addBtn.trigger('click')
    await flushPromises()

    // The job lands in the queue straight away…
    expect(client.enqueuePrint).toHaveBeenCalledTimes(1)
    expect(client.enqueuePrint).toHaveBeenCalledWith('art.png', job.selectedProfileName, job.gcode)
    // …and the magazine-load gate never opened, even with 2 inks on a
    // 2-slot profile (the case that used to trigger it).
    expect(useMagazineGateState().open).toBe(false)
  })

  it('still queues when connected (uses the "+ queue" button alongside send)', async () => {
    await seedMultiInkJob()
    usePlotterStore().status.connected = true

    const wrapper = mount(PrintQueuePanel, { global: { plugins: [i18n] } })
    await nextTick()
    // Both the direct-send and the enqueue buttons are present when connected.
    expect(wrapper.find('[data-test="queue-send-now"]').exists()).toBe(true)
    const addBtn = wrapper.find('[data-test="queue-enqueue"]')
    expect(addBtn.exists()).toBe(true)

    await addBtn.trigger('click')
    await flushPromises()

    expect(client.enqueuePrint).toHaveBeenCalledTimes(1)
    expect(useMagazineGateState().open).toBe(false)
  })
})
