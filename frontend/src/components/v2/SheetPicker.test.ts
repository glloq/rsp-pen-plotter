// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'

import SheetPicker from './SheetPicker.vue'
import { useUiStore } from '../../stores/ui'

const i18n = createI18n({
  legacy: false,
  locale: 'fr',
  fallbackLocale: 'fr',
  messages: {
    fr: {
      v2: {
        modal: {
          sheetPickerLabel: 'Format de feuille',
          sheetPortrait: 'Portrait',
          sheetLandscape: 'Paysage',
        },
      },
    },
  },
})

function mountPicker() {
  return mount(SheetPicker, { global: { plugins: [i18n] } })
}

describe('SheetPicker', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('exposes A6 / A5 / A4 / A3 / A2 / Letter chips', () => {
    const wrapper = mountPicker()
    for (const name of ['A6', 'A5', 'A4', 'A3', 'A2', 'Letter']) {
      expect(wrapper.find(`[data-test="sheet-preset-${name}"]`).exists()).toBe(true)
    }
  })

  it('writes through ui.setPreviewSheet when a preset is clicked, portrait by default', async () => {
    const wrapper = mountPicker()
    const ui = useUiStore()
    await wrapper.find('[data-test="sheet-preset-A4"]').trigger('click')
    // Portrait A4 = 210 × 297 mm.
    expect(ui.previewSheet?.width_mm).toBe(210)
    expect(ui.previewSheet?.height_mm).toBe(297)
  })

  it('flipping orientation swaps width/height of the live sheet', async () => {
    const ui = useUiStore()
    ui.setPreviewSheet({ width_mm: 210, height_mm: 297, x_mm: 0, y_mm: 0 })
    const wrapper = mountPicker()
    await wrapper.find('[data-test="sheet-orientation-landscape"]').trigger('click')
    expect(ui.previewSheet?.width_mm).toBe(297)
    expect(ui.previewSheet?.height_mm).toBe(210)
  })

  it('orientation toggle seeds an A4 when nothing is selected yet', async () => {
    const wrapper = mountPicker()
    const ui = useUiStore()
    expect(ui.previewSheet).toBeNull()
    await wrapper.find('[data-test="sheet-orientation-landscape"]').trigger('click')
    expect(ui.previewSheet?.width_mm).toBe(297)
    expect(ui.previewSheet?.height_mm).toBe(210)
  })

  it('marks the active preset based on the live sheet dimensions (±0.5 mm tolerance)', async () => {
    const ui = useUiStore()
    ui.setPreviewSheet({ width_mm: 210.2, height_mm: 296.9, x_mm: 0, y_mm: 0 })
    const wrapper = mountPicker()
    const a4 = wrapper.find('[data-test="sheet-preset-A4"]')
    expect(a4.classes()).toContain('active')
    expect(a4.attributes('aria-pressed')).toBe('true')
    const a5 = wrapper.find('[data-test="sheet-preset-A5"]')
    expect(a5.classes()).not.toContain('active')
  })
})
