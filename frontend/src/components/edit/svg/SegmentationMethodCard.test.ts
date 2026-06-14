// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, expect, it } from 'vitest'
import SegmentationMethodCard from './SegmentationMethodCard.vue'
import { useBitmapDraft } from '../../../composables/useBitmapDraft'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
})

beforeEach(() => {
  setActivePinia(createPinia())
})

function mountCard() {
  const bitmap = useBitmapDraft().bitmap.value
  return mount(SegmentationMethodCard, {
    props: { bitmap: bitmap as never, isDocument: false },
    global: { plugins: [i18n] },
  })
}

it('picking kmeans turns off palette-follows-pens and clears the palette', async () => {
  const d = useBitmapDraft()
  d.rehydrateDraft({ placement: null, installedPenColors: [] })
  // Start from a pens-follow / fixed_palette state.
  d.paletteFollowsPens.value = true
  d.bitmap.value.segmentation_method = 'fixed_palette'
  d.bitmap.value.palette = ['#111111', '#222222']

  const wrapper = mountCard()
  // The kmeans button is the first segmentation-method button.
  const kmeansBtn = wrapper
    .findAll('button')
    .find((b) => b.text().toLowerCase().includes('kmeans') && !b.text().includes('lab'))
  expect(kmeansBtn).toBeTruthy()
  await kmeansBtn!.trigger('click')

  expect(d.bitmap.value.segmentation_method).toBe('kmeans')
  expect(d.paletteFollowsPens.value).toBe(false)
  expect(d.bitmap.value.palette).toEqual([])
  expect(d.segmentationTouched.value.has('method')).toBe(true)
})
