// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import EditPreviewPane from './EditPreviewPane.vue'
import { resetEditState, useEditState } from '../../composables/useEditState'
import { useJobStore } from '../../stores/job'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: { en: { editPreview: {}, variants: {}, upload: {} } },
})

function mountPane() {
  return mount(EditPreviewPane, { global: { plugins: [i18n] } })
}

describe('EditPreviewPane display logic', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    resetEditState()
  })

  it('renders the original raster on source mode (Image tab)', async () => {
    const edit = useEditState()
    edit.kind.value = 'bitmap'
    edit.previewUrl.value = 'blob:fake-original'
    edit.previewMode.value = 'source'
    const wrapper = mountPane()
    await nextTick()
    const imgs = wrapper.findAll('img')
    expect(imgs.some((i) => i.attributes('src') === 'blob:fake-original')).toBe(true)
  })

  it('renders the live SVG on auto mode (SVG tab)', async () => {
    const edit = useEditState()
    edit.kind.value = 'bitmap'
    edit.previewSvg.value = '<svg viewBox="0 0 10 10"><path d="M0 0"/></svg>'
    edit.previewMode.value = 'auto'
    const wrapper = mountPane()
    await nextTick()
    expect(wrapper.html()).toContain('<svg')
  })

  it('shows both halves and the reveal handle in comparison mode', async () => {
    const edit = useEditState()
    edit.kind.value = 'bitmap'
    edit.previewUrl.value = 'blob:fake-original'
    edit.previewSvg.value = '<svg viewBox="0 0 10 10"><path d="M0 0"/></svg>'
    edit.previewMode.value = 'split'
    const wrapper = mountPane()
    await nextTick()
    const html = wrapper.html()
    // original raster on the left, computed SVG on the right
    expect(wrapper.findAll('img').some((i) => i.attributes('src') === 'blob:fake-original')).toBe(
      true,
    )
    expect(html).toContain('<svg')
    // draggable reveal handle (the ⇄ grip knob)
    expect(html).toContain('⇄')
  })

  it('falls back to the library original URL when no in-memory object URL exists', async () => {
    const store = useJobStore()
    store.placements = [
      {
        id: 'p1',
        source_file: 'photo.png',
        last_file: null,
        library_file_id: 'lib-123',
        variants: [],
      } as never,
    ]
    store.selectedPlacementId = 'p1'
    const edit = useEditState()
    edit.kind.value = 'bitmap'
    edit.previewUrl.value = null
    edit.previewMode.value = 'source'
    const wrapper = mountPane()
    await nextTick()
    const img = wrapper.findAll('img').find((i) => /lib-123/.test(i.attributes('src') ?? ''))
    expect(img).toBeTruthy()
    expect(img!.attributes('src')).toContain('/files/lib-123/original')
  })
})
