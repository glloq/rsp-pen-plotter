// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'

import PreviewToolbar from './PreviewToolbar.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      v2: {
        modal: {
          viewPlot: 'Result',
          viewOriginal: 'Original',
          viewCompare: 'Compare',
          zoomIn: 'Zoom in',
          zoomOut: 'Zoom out',
          resetView: 'Reset',
        },
      },
    },
  },
})

function mountToolbar(props: Record<string, unknown>) {
  return mount(PreviewToolbar, {
    props: {
      viewMode: 'plot',
      canShowOriginal: true,
      canCompareOriginal: true,
      zoom: 1,
      ...props,
    },
    global: { plugins: [i18n] },
  })
}

describe('PreviewToolbar', () => {
  it('hides the mode toggle when no original is available', () => {
    const wrapper = mountToolbar({ canShowOriginal: false })
    expect(wrapper.find('[data-test="modal-v2-mode-toggle"]').exists()).toBe(false)
    // Zoom cluster is always present.
    expect(wrapper.find('[data-test="modal-v2-zoom"]').exists()).toBe(true)
  })

  it('emits set-mode for each view button', async () => {
    const wrapper = mountToolbar({})
    await wrapper.find('[data-test="modal-v2-mode-source"]').trigger('click')
    await wrapper.find('[data-test="modal-v2-mode-split"]').trigger('click')
    await wrapper.find('[data-test="modal-v2-mode-plot"]').trigger('click')
    expect(wrapper.emitted('set-mode')).toEqual([['source'], ['split'], ['plot']])
  })

  it('disables Compare when comparison is unavailable', () => {
    const wrapper = mountToolbar({ canCompareOriginal: false })
    const split = wrapper.find('[data-test="modal-v2-mode-split"]')
    expect((split.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('emits the zoom actions', async () => {
    const wrapper = mountToolbar({})
    await wrapper.find('[data-test="modal-v2-zoom-in"]').trigger('click')
    await wrapper.find('[data-test="modal-v2-zoom-out"]').trigger('click')
    await wrapper.find('[data-test="modal-v2-zoom-reset"]').trigger('click')
    expect(wrapper.emitted('zoom-in')).toHaveLength(1)
    expect(wrapper.emitted('zoom-out')).toHaveLength(1)
    expect(wrapper.emitted('reset-view')).toHaveLength(1)
  })

  it('renders the zoom percent from the zoom factor', () => {
    const wrapper = mountToolbar({ zoom: 1.25 })
    expect(wrapper.find('[data-test="modal-v2-zoom-reset"]').text()).toBe('125%')
  })
})
