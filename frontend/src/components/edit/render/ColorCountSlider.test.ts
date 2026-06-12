// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import ColorCountSlider from './ColorCountSlider.vue'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useAvailableColorsStore } from '../../../stores/availableColors'
import { usePaletteSourceStore } from '../../../stores/paletteSource'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      colorStyles: {
        numColors: 'Colour count',
        numColorsHint: 'hint',
        numColorsRendered: 'rendered {rendered}/{requested}',
        numColorsCapped: 'capped {requested}/{available}',
        numColorsPoolCapped: 'pool capped {requested}/{pool}',
      },
    },
  },
})

function seedInventory(hexes: string[]): void {
  const inv = useAvailableColorsStore()
  inv.colors = hexes.map((hex, i) => ({
    id: String(i),
    hex,
    name: '',
    position: i,
    created_at: '2026-01-01T00:00:00Z',
  })) as never
  inv.loaded = true
  const ps = usePaletteSourceStore()
  ps.source = 'available'
  ps.loaded = true
}

interface BitmapLike {
  num_colors: number
  palette: string[]
  segmentation_method: string
  [key: string]: unknown
}

function mountSlider(bitmap: BitmapLike) {
  return mount(ColorCountSlider, {
    props: { bitmap },
    global: { plugins: [i18n] },
  })
}

describe('ColorCountSlider', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('pads a manual palette with unused pool inks before synthetic greys', async () => {
    seedInventory(['#111111', '#aaaaaa', '#bbbbbb', '#222222'])
    const draft = useBitmapDraft()
    draft.paletteFollowsPens.value = false
    const bitmap = draft.bitmap.value
    bitmap.segmentation_method = 'fixed_palette'
    bitmap.palette = ['#111111', '#222222']
    bitmap.num_colors = 2

    const wrapper = mountSlider(bitmap)
    await wrapper.find('input[type="range"]').setValue('4')

    // The two new chips are the operator's OWN unused inks, in pool
    // order — not synthetic greys.
    expect(bitmap.palette).toEqual(['#111111', '#222222', '#aaaaaa', '#bbbbbb'])
  })

  it('falls back to synthetic distinct colours once the pool is exhausted', async () => {
    seedInventory(['#111111', '#222222'])
    const draft = useBitmapDraft()
    draft.paletteFollowsPens.value = false
    const bitmap = draft.bitmap.value
    bitmap.segmentation_method = 'fixed_palette'
    bitmap.palette = ['#111111', '#222222']
    bitmap.num_colors = 2

    const wrapper = mountSlider(bitmap)
    await wrapper.find('input[type="range"]').setValue('4')

    expect(bitmap.palette).toHaveLength(4)
    // No duplicates among the padded chips.
    expect(new Set(bitmap.palette.map((h: string) => h.toLowerCase())).size).toBe(4)
  })

  it('warns when the requested count exceeds the owned-ink pool', async () => {
    seedInventory(['#111111', '#222222', '#333333'])
    const draft = useBitmapDraft()
    draft.paletteFollowsPens.value = false
    const bitmap = draft.bitmap.value
    bitmap.segmentation_method = 'kmeans'
    bitmap.palette = []
    bitmap.num_colors = 8

    const wrapper = mountSlider(bitmap)
    const warning = wrapper.find('[data-test="num-colors-pool-capped"]')
    expect(warning.exists()).toBe(true)
    expect(warning.text()).toContain('8/3')
  })

  it('stays silent when the pool covers the requested count', () => {
    seedInventory(['#111111', '#222222', '#333333', '#444444'])
    const draft = useBitmapDraft()
    draft.paletteFollowsPens.value = false
    const bitmap = draft.bitmap.value
    bitmap.segmentation_method = 'kmeans'
    bitmap.palette = []
    bitmap.num_colors = 4

    const wrapper = mountSlider(bitmap)
    expect(wrapper.find('[data-test="num-colors-pool-capped"]').exists()).toBe(false)
  })
})
