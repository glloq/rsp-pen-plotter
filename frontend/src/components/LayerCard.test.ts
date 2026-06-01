// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import LayerCard from './LayerCard.vue'
import { useJobStore } from '../stores/job'
import type { LayerInfo, MachineProfile } from '../api/client'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      layers: {
        dragHint: 'Drag',
        kindImage: 'Image',
        kindText: 'Text',
        paths: 'paths',
        expand: 'Expand',
        collapse: 'Collapse',
        penSlot: 'Pen slot',
        speed: 'Speed',
        simplify: 'Simplify',
        optimize: 'Optimise',
        default: 'default',
        defaultAlgo: 'default',
        none: 'none',
        nearestPenHint: '',
        penWarning: '',
        penWarningNone: '',
        colorLabel: 'Color label',
        renderAlgorithm: 'Algo',
        pauseBefore: 'Pause',
        pauseAuto: 'auto',
        pauseAlways: 'always',
        pauseNever: 'never',
        printStyle: 'Style',
        advancedShow: 'Advanced',
        advancedHide: 'Hide',
        algoSettings: 'Settings',
      },
      passes: {
        badgeHint: '',
        enable: 'Multi',
        enableHint: '',
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
    pen_slot_count: 1,
    supports_arcs: false,
    arc_tolerance_mm: 0.1,
    ebb: null,
    pens: null,
  }
}

function makeLayer(): LayerInfo {
  return {
    layer_id: 'layer-1',
    source_color: '#ff8800',
    color_label: null,
    target_pen_slot: null,
    drawing_speed_mm_s: null,
    simplify_tolerance_mm: 0.05,
    optimize: true,
    pause_before: 'auto',
    path_count: 12,
    total_length_mm: 145.5,
    draw_order: 0,
  } as LayerInfo
}

async function seedProfile(): Promise<void> {
  const job = useJobStore()
  const { profiles, selectedProfileName } = storeToRefs(job)
  const profile = makeProfile()
  profiles.value = [profile]
  selectedProfileName.value = profile.name
  await nextTick()
}

function mountCard() {
  return mount(LayerCard, {
    props: { layer: makeLayer() },
    global: { plugins: [i18n] },
  })
}

describe('LayerCard', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    await seedProfile()
  })

  it('renders the header with the layer label + path stats', () => {
    const wrapper = mountCard()
    const text = wrapper.text()
    // formatLayerLabel renders the layer_id as "Layer N" for non-colour
    // ids; the path stats are appended to the same header line.
    expect(text).toMatch(/Layer\s*1/)
    expect(text).toContain('12 paths')
    expect(text).toContain('145.5 mm')
  })

  it('renders the simplify + speed inputs in the expanded body', () => {
    const wrapper = mountCard()
    // Body is shown by default (``collapsed = false``).
    expect(wrapper.find('input[type="number"]').exists()).toBe(true)
  })

  it('hides the body when the collapse button is clicked', async () => {
    const wrapper = mountCard()
    const collapseBtn = wrapper.find('button[aria-expanded="true"]')
    expect(collapseBtn.exists()).toBe(true)
    await collapseBtn.trigger('click')
    // After collapse: aria-expanded flips to false; the speed/simplify
    // inputs disappear with their parent grid.
    expect(wrapper.find('button[aria-expanded="false"]').exists()).toBe(true)
  })

  it('renders one pause button per policy', () => {
    const wrapper = mountCard()
    const text = wrapper.text()
    expect(text).toContain('auto')
    expect(text).toContain('always')
    expect(text).toContain('never')
  })
})
