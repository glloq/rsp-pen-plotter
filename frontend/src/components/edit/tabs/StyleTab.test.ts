// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, expect, it } from 'vitest'
import { nextTick } from 'vue'
import StyleTab from './StyleTab.vue'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'
import { useFileManager } from '../../../composables/useFileManager'
import { useAvailableColorsStore } from '../../../stores/availableColors'
import { usePaletteSourceStore } from '../../../stores/paletteSource'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
})

function seed(hexes: string[]): void {
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

const flush = () => new Promise((r) => setTimeout(r, 0))

// Initialise the OWNER file manager first, exactly like EditModalV2 does
// at modal open: this consumes the composable's one-time wiring +
// rehydrate so a later tab mount can't re-trigger them (which would be a
// test artifact, not real-app behaviour).
async function openModal(): Promise<ReturnType<typeof useBitmapDraft>> {
  const t = (k: string) => k
  useFileManager(t as never, { owner: true })
  await flush()
  await nextTick()
  const d = useBitmapDraft()
  d.rehydrateDraft({ placement: null, installedPenColors: [] })
  return d
}

async function enterStyleTab(): Promise<void> {
  mount(StyleTab, { global: { plugins: [i18n] } })
  await nextTick()
  await nextTick()
}

beforeEach(() => {
  setActivePinia(createPinia())
})

it('keeps an explicit kmeans choice intact when entering the Style tab', async () => {
  const d = await openModal()
  seed(['#ff0000', '#00ff00', '#0000ff'])

  // Operator picks kmeans (cluster the image's own colours) in the SVG tab.
  d.bitmap.value.segmentation_method = 'kmeans'
  d.markSegmentationTouched('method')

  await enterStyleTab()

  // Method survives the tab switch...
  expect(d.bitmap.value.segmentation_method).toBe('kmeans')
  // ...and the palette is NOT stomped with the pen/inventory pool.
  expect(d.bitmap.value.palette).toEqual([])
})

it('still seeds fixed_palette + the pool when no method was chosen (pens-follow default)', async () => {
  const d = await openModal()
  seed(['#ff0000', '#00ff00', '#0000ff'])

  // No explicit method choice — the palette-follows-pens default should
  // mirror the pool into the draft and seed fixed_palette.
  await enterStyleTab()

  expect(d.bitmap.value.segmentation_method).toBe('fixed_palette')
  expect(d.bitmap.value.palette).toEqual(['#ff0000', '#00ff00', '#0000ff'])
})
