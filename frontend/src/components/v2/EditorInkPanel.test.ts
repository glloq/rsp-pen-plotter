// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import EditorInkPanel from './EditorInkPanel.vue'
import type { InkSwatch } from '../../composables/useEditorInkSwatches'
import type { LayerInfo } from '../../api/client'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
})

function layer(id: string, hex: string): LayerInfo {
  return {
    layer_id: id,
    source_color: hex,
    assigned_color_hex: hex,
    draw_order: 0,
    target_pen_slot: null,
    total_length_mm: 0,
    path_count: 0,
    bbox: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 },
    optimize: true,
    simplify_tolerance_mm: 0,
    drawing_speed_mm_s: null,
    color_label: null,
    pause_before: 'auto',
    color_assignment: 'auto',
  } as LayerInfo
}

function swatch(id: string, hex: string): InkSwatch {
  return {
    layerId: id,
    hex,
    name: hex,
    displayName: hex,
    displayHex: '',
    isFallback: false,
    layer: layer(id, hex),
  }
}

function mountPanel(swatches: InkSwatch[]) {
  return mount(EditorInkPanel, {
    props: {
      swatches,
      isVisible: () => true,
      effectivePalette: ['#ff0000', '#00ff00'],
      pickerPalette: ['#ff0000', '#00ff00', '#0000ff'],
    },
    global: { plugins: [i18n] },
  })
}

describe('EditorInkPanel', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('emits toggle when the chip is clicked', async () => {
    const w = mountPanel([swatch('color-aabbcc', '#aabbcc')])
    await w.get('[data-test="modal-v2-ink-color-aabbcc"]').trigger('click')
    expect(w.emitted('toggle')?.[0]).toEqual(['color-aabbcc'])
  })

  it('opens the assign popover and emits pick with the layer id', async () => {
    const w = mountPanel([swatch('color-aabbcc', '#aabbcc')])
    // No popover until the assign button is pressed.
    expect(w.find('[data-test="modal-v2-ink-popover-color-aabbcc"]').exists()).toBe(false)
    await w.get('[data-test="modal-v2-ink-assign-color-aabbcc"]').trigger('click')
    expect(w.find('[data-test="modal-v2-ink-popover-color-aabbcc"]').exists()).toBe(true)
    // Pick the third inventory swatch (blue) — the picker offers the full
    // pickerPalette regardless of the auto pool.
    const swatchBtns = w
      .get('[data-test="modal-v2-ink-popover-color-aabbcc"]')
      .findAll('button[style]')
    await swatchBtns[swatchBtns.length - 1]!.trigger('click')
    const pick = w.emitted('pick')?.[0]?.[0] as { layerId: string; hex: string }
    expect(pick.layerId).toBe('color-aabbcc')
    expect(pick.hex).toBe('#0000ff')
    // Popover closes after a pick.
    expect(w.find('[data-test="modal-v2-ink-popover-color-aabbcc"]').exists()).toBe(false)
  })

  it('offers the assign button on a live-preview cluster chip too', () => {
    // Cluster chips (never-committed image) carry a synthetic layer, so the
    // assign button is available all the time — not only on saved files.
    const w = mountPanel([swatch('cluster-aabbcc', '#aabbcc')])
    expect(w.find('[data-test="modal-v2-ink-assign-cluster-aabbcc"]').exists()).toBe(true)
  })
})
