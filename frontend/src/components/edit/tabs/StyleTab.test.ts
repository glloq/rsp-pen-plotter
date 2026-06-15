// @vitest-environment happy-dom
import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { afterEach, beforeEach, expect, it } from 'vitest'
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

// Track mounted tabs so each test's StyleTab — and its still-active
// pens-watch — is torn down before the next test runs. Without this, a
// leftover StyleTab from a prior test fires its watch against the shared
// singleton draft during the next test's setup (e.g. ``seed()``), stomping
// state before that test has configured it.
let mounted: VueWrapper[] = []

async function enterStyleTab(): Promise<void> {
  mounted.push(mount(StyleTab, { global: { plugins: [i18n] } }))
  await nextTick()
  await nextTick()
}

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  for (const w of mounted) w.unmount()
  mounted = []
})

it('keeps a COMMITTED kmeans conversion intact (touched=false) on Style-tab entry', async () => {
  // The operator's real bug: an image previously converted with kmeans
  // reopens with method=kmeans, committed=true and touched=false (rehydrate
  // clears the flag). palette-follows-pens is at its default (true). Entering
  // the Style tab used to stomp this to fixed_palette + the pen palette.
  const t = (k: string) => k
  useFileManager(t as never, { owner: true })
  await flush()
  await nextTick()
  const d = useBitmapDraft()
  d.rehydrateDraft({
    placement: { source_file: 'photo.jpg', last_options: { segmentation_method: 'kmeans', num_colors: 6 } },
    installedPenColors: ['#ff0000', '#00ff00', '#0000ff'],
  })
  seed(['#ff0000', '#00ff00', '#0000ff'])

  // Preconditions matching the KDIAG capture.
  expect(d.bitmap.value.segmentation_method).toBe('kmeans')
  expect(d.segmentationTouched.value.has('method')).toBe(false)
  expect(d.committed.value).toBe(true)
  expect(d.paletteFollowsPens.value).toBe(true)

  await enterStyleTab()

  expect(d.bitmap.value.segmentation_method).toBe('kmeans')
  expect(d.bitmap.value.palette).toEqual([])
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

it('does not stomp the palette when kmeans turned palette-follows-pens off', async () => {
  const d = await openModal()
  seed(['#ff0000', '#00ff00', '#0000ff'])

  // This mirrors what SegmentationMethodCard.selectMethod('kmeans') does.
  d.bitmap.value.segmentation_method = 'kmeans'
  d.markSegmentationTouched('method')
  d.paletteFollowsPens.value = false
  d.bitmap.value.palette = []

  await enterStyleTab()

  expect(d.bitmap.value.segmentation_method).toBe('kmeans')
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
