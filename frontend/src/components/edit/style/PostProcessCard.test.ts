// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, expect, it } from 'vitest'
import PostProcessCard from './PostProcessCard.vue'
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
  return mount(PostProcessCard, {
    props: { bitmap: bitmap as never },
    global: { plugins: [i18n] },
  })
}

async function setAndCommit(wrapper: ReturnType<typeof mountCard>, index: number, value: string) {
  // Number inputs in template order: [0] min_region, [1] merge_delta_e,
  // [2] background_luminance.
  const input = wrapper.findAll('input[type="number"]')[index]!
  ;(input.element as HTMLInputElement).value = value
  await input.trigger('change')
}

it('clamps out-of-range / cleared numeric inputs instead of persisting NaN', async () => {
  const d = useBitmapDraft()
  d.rehydrateDraft({ placement: null, installedPenColors: [] })
  const wrapper = mountCard()
  // CollapsibleCard renders its body with v-if and starts collapsed; expand it.
  await wrapper.find('[aria-expanded]').trigger('click')
  expect(wrapper.findAll('input[type="number"]').length).toBe(3)

  // Background luminance (0–1, drop_background on by default): 5 would drop
  // every layer → blank preview. Must clamp to the max, and a cleared field
  // must not become NaN.
  await setAndCommit(wrapper, 2, '5')
  expect(d.bitmap.value.background_luminance).toBe(1)
  await setAndCommit(wrapper, 2, '')
  expect(d.bitmap.value.background_luminance).toBe(0)

  // min_region_pixels: cleared field must be 0, never NaN (a 422 on the wire).
  await setAndCommit(wrapper, 0, '')
  expect(d.bitmap.value.min_region_pixels).toBe(0)
  expect(Number.isNaN(d.bitmap.value.min_region_pixels)).toBe(false)

  // merge_delta_e clamps to its max.
  await setAndCommit(wrapper, 1, '9999')
  expect(d.bitmap.value.merge_delta_e).toBe(50)
})
