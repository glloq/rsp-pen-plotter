// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

vi.mock('../../api/client', async (orig) => {
  const actual = await orig<typeof import('../../api/client')>()
  return {
    ...actual,
    saveProfile: vi.fn(async (p: unknown) => p),
    getProfiles: vi.fn(async () => []),
  }
})

import * as client from '../../api/client'
import MagazinePlanPanel from './MagazinePlanPanel.vue'
import { useJobStore, type Placement } from '../../stores/job'
import type { LayerInfo, MachineProfile, PenSlot } from '../../api/client'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      magazinePlan: {
        title: 'Prepare the magazine',
        summary: '{inks} ink(s) · {slots} slot(s)',
        initialTitle: 'Mount before starting:',
        swapsTitle: 'Mid-print swaps ({count}):',
        pauseNote: 'Pauses will name the ink.',
        noPauseSupport: 'No tool-change support.',
        apply: 'Apply this plan',
        applying: 'Applying…',
        applied: 'Applied',
        applyFailed: 'Failed',
        ready: 'Magazine ready',
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

function makeProfile(over: Partial<MachineProfile> = {}): MachineProfile {
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
    ...over,
  } as MachineProfile
}

function makeLayer(id: string, hex: string, order: number): LayerInfo {
  return {
    layer_id: id,
    source_color: hex,
    assigned_color_hex: hex,
    // Manual so the job store's palette-source resnap watcher (which
    // fires when the test seeds the profile) can't rewrite the inks
    // the plan is computed from.
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

async function seed(
  layers: LayerInfo[],
  profile = makeProfile(),
): Promise<ReturnType<typeof useJobStore>> {
  const job = useJobStore()
  const { profiles, selectedProfileName } = storeToRefs(job)
  profiles.value = [profile]
  selectedProfileName.value = profile.name
  job.placements = [makePlacement(layers)]
  job.selectedPlacementId = 'p1'
  await nextTick()
  return job
}

function mountPanel() {
  return mount(MagazinePlanPanel, { global: { plugins: [i18n] } })
}

describe('MagazinePlanPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(client.saveProfile).mockClear()
  })

  it('stays hidden on mono-pen machines', async () => {
    await seed(
      [makeLayer('a', '#111111', 0)],
      makeProfile({ pen_slot_count: 1, pens: [pen(0, '#000000')] }),
    )
    const wrapper = mountPanel()
    expect(wrapper.find('[data-test="magazine-plan"]').exists()).toBe(false)
  })

  it('shows the initial loading and the swap schedule when inks exceed slots', async () => {
    await seed([
      makeLayer('a', '#111111', 0),
      makeLayer('b', '#222222', 1),
      makeLayer('c', '#333333', 2),
    ])
    const wrapper = mountPanel()
    expect(wrapper.find('[data-test="magazine-plan"]').exists()).toBe(true)
    // 2 slots → 2 initial loads + 1 swap.
    expect(wrapper.find('[data-test="magazine-plan-slot-0"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="magazine-plan-slot-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="magazine-plan-swaps"]').text()).toContain('#333333')
  })

  it('applies the plan: pins layer slots/inks and updates the profile pens', async () => {
    const job = await seed([
      makeLayer('a', '#111111', 0),
      makeLayer('b', '#222222', 1),
      makeLayer('c', '#333333', 2),
    ])
    const wrapper = mountPanel()
    await wrapper.find('[data-test="magazine-plan-apply"]').trigger('click')
    await nextTick()

    const layers = job.placements[0]!.layers
    expect(layers.map((l) => l.target_pen_slot)).toEqual([0, 1, 0])
    expect(layers.every((l) => l.color_assignment === 'manual')).toBe(true)

    expect(client.saveProfile).toHaveBeenCalledTimes(1)
    const saved = vi.mocked(client.saveProfile).mock.calls[0]![0] as MachineProfile
    const colors = (saved.pens ?? []).map((p) => p.color)
    expect(colors).toEqual(['#111111', '#222222'])
    expect((saved.pens ?? []).every((p) => p.installed)).toBe(true)
  })
})
