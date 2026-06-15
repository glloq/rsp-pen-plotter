// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createI18n } from 'vue-i18n'

vi.mock('../../api/client', async (orig) => {
  const actual = await (orig() as Promise<Record<string, unknown>>)
  return {
    ...actual,
    api: { post: vi.fn().mockResolvedValue({ data: {} }), get: vi.fn() },
    rerenderJob: vi.fn().mockResolvedValue({ svg: '<svg/>', warnings: [] }),
    getPaletteSource: vi.fn().mockResolvedValue({ source: 'pens' }),
    setPaletteSource: vi.fn().mockResolvedValue(undefined),
  }
})

import { api } from '../../api/client'
import EditModalV2 from './EditModalV2.vue'

const i18n = createI18n({ legacy: false, locale: 'fr', missingWarn: false, fallbackWarn: false, messages: { fr: {} } })

const validDecision = {
  segmentation_method: 'fixed_palette',
  default_algorithm: 'scanlines',
  default_options: { num_colors: 4 },
  quality_tier: 'draft',
  fallback_chain: [],
  reasoning: [],
  hard_constraints_applied: [],
}

beforeEach(() => {
  setActivePinia(createPinia())
  window.localStorage.clear()
  vi.mocked(api.post).mockReset()
  vi.mocked(api.post).mockResolvedValue({ data: validDecision })
})

describe('EditModalV2 expert kmeans regression', () => {
  it('keeps kmeans after SVG→Style→SVG round trip', async () => {
    const { useJobStore } = await import('../../stores/job')
    const { useUiModeStore } = await import('../../stores/uiMode')
    const { usePaletteSourceStore } = await import('../../stores/paletteSource')
    const { useAvailableColorsStore } = await import('../../stores/availableColors')
    const { useBitmapDraft } = await import('../../composables/useBitmapDraft')

    const job = useJobStore()
    // Machine profile with installed pens (pens-follow default).
    job.profiles = [
      {
        name: 'test',
        pen_slot_count: 3,
        pens: [
          { index: 0, color: '#ff0000', installed: true },
          { index: 1, color: '#00ff00', installed: true },
          { index: 2, color: '#0000ff', installed: true },
        ],
      },
    ] as never
    job.selectedProfileName = 'test'

    usePaletteSourceStore().source = 'pens'
    usePaletteSourceStore().loaded = true
    useAvailableColorsStore().loaded = true

    const id = job.addEmptyPlacement()
    job.placements = job.placements.map((p) =>
      p.id === id
        ? {
            ...p,
            source_file: 'photo.jpg',
            source_mime: 'image/png',
            svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>',
            // Pens-committed last_options: rehydrate reads ink_pool and
            // lands on fixed_palette + paletteFollowsPens — the real
            // starting state the operator opens onto.
            last_options: {
              segmentation_method: 'kmeans_lab',
              ink_pool: ['#ff0000', '#00ff00', '#0000ff'],
            },
            layers: [],
          }
        : p,
    )

    useUiModeStore().setMode('expert')

    const wrapper = mount(EditModalV2, {
      props: { sourceName: 'photo.jpg', previewSvg: '<svg/>', skipOnboarding: true },
      global: { plugins: [i18n] },
    })
    await flushPromises()
    await nextTick()

    const draft = useBitmapDraft()

    const tabBtn = (re: RegExp) =>
      wrapper.findAll('[role="tab"]').find((b) => re.test(b.text()))

    // --- Simulate SegmentationMethodCard.selectMethod('kmeans') (the
    // exact mutations the current code performs on a kmeans pick). ---
    draft.bitmap.value.segmentation_method = 'kmeans'
    draft.markSegmentationTouched('method')
    draft.paletteFollowsPens.value = false
    draft.bitmap.value.palette = []
    await flushPromises()
    await nextTick()

    // --- Switch to the Style tab (real component mount). ---
    const styleTabBtn = tabBtn(/style/i)
    if (styleTabBtn) await styleTabBtn.trigger('click')
    await flushPromises()
    await nextTick()
    await flushPromises()

    // --- Back to SVG. ---
    const svgTabBtn2 = tabBtn(/svg/i)
    if (svgTabBtn2) await svgTabBtn2.trigger('click')
    await flushPromises()

    expect(draft.bitmap.value.segmentation_method).toBe('kmeans')
  })
})
