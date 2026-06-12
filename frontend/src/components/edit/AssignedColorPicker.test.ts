// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import AssignedColorPicker from './AssignedColorPicker.vue'
import { useAvailableColorsStore } from '../../stores/availableColors'
import type { LayerInfo } from '../../api/client'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      assignedColor: {
        title: 'Layer colour',
        auto: 'auto',
        manual: 'manual',
        reset: 'auto',
        resetTitle: '',
        pickHint: 'Pick',
        emptyPool: 'No colours yet',
      },
    },
  },
})

function makeLayer(overrides: Partial<LayerInfo> = {}): LayerInfo {
  return {
    layer_id: 'color-112233',
    source_color: '#112233',
    color_label: null,
    assigned_color_hex: '#112233',
    color_assignment: 'auto',
    target_pen_slot: null,
    drawing_speed_mm_s: null,
    simplify_tolerance_mm: 0.05,
    optimize: true,
    pause_before: 'auto',
    path_count: 1,
    total_length_mm: 10,
    draw_order: 0,
    ...overrides,
  } as LayerInfo
}

const MAGAZINE = ['#000000', '#ff0000']
const INVENTORY_EXTRAS = ['#00ff00', '#0000ff', '#ffaa00']

function mountPicker(props: Record<string, unknown> = {}) {
  return mount(AssignedColorPicker, {
    props: {
      layer: makeLayer(),
      effectivePalette: MAGAZINE,
      ...props,
    },
    global: { plugins: [i18n] },
  })
}

function swatchHexes(wrapper: ReturnType<typeof mountPicker>): string[] {
  return wrapper
    .findAll('button[aria-label]')
    .map((b) => (b.element as HTMLElement).style.backgroundColor)
}

describe('AssignedColorPicker', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('offers the full picker palette even when the auto pool is magazine-only', () => {
    // Regression: with palette source 'pens' the strip used to show only
    // the magazine colours — the operator's inventory was hidden.
    const wrapper = mountPicker({ pickerPalette: [...MAGAZINE, ...INVENTORY_EXTRAS] })
    expect(swatchHexes(wrapper)).toHaveLength(MAGAZINE.length + INVENTORY_EXTRAS.length)
  })

  it('falls back to the effective palette when no picker palette is given', () => {
    const wrapper = mountPicker()
    expect(swatchHexes(wrapper)).toHaveLength(MAGAZINE.length)
  })

  it('emits a manual pick with the chosen hex', async () => {
    const wrapper = mountPicker({ pickerPalette: [...MAGAZINE, ...INVENTORY_EXTRAS] })
    const swatches = wrapper.findAll('button[aria-label]')
    await swatches[swatches.length - 1]!.trigger('click')
    expect(wrapper.emitted('pick')).toEqual([[{ hex: '#ffaa00', assignment: 'manual' }]])
  })

  it('resets auto against the effective pool, not the picker palette', async () => {
    // Manual layer assigned to an inventory ink; "↻ auto" must snap back
    // to the nearest colour in the AUTO pool (palette-source-driven) so
    // it matches the job store's own resnap behaviour.
    const wrapper = mountPicker({
      layer: makeLayer({
        source_color: '#ee1100',
        assigned_color_hex: '#00ff00',
        color_assignment: 'manual',
      }),
      pickerPalette: [...MAGAZINE, ...INVENTORY_EXTRAS],
    })
    await wrapper.find('button[title]').trigger('click')
    const reset = wrapper.emitted('reset')
    expect(reset).toBeTruthy()
    expect(reset![0]).toEqual([{ hex: '#ff0000' }])
  })

  it('shows inventory names as swatch labels', () => {
    const store = useAvailableColorsStore()
    store.colors = [
      {
        id: '1',
        hex: '#00ff00',
        name: 'Vert prairie',
        position: 0,
        created_at: '2026-01-01T00:00:00Z',
      },
    ] as never
    const wrapper = mountPicker({ pickerPalette: [...MAGAZINE, ...INVENTORY_EXTRAS] })
    expect(wrapper.find('button[aria-label="Vert prairie"]').exists()).toBe(true)
  })
})
