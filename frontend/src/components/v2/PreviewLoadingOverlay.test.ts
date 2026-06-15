// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'

import PreviewLoadingOverlay from './PreviewLoadingOverlay.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: { en: { v2: { modal: { previewLoading: 'Updating preview…' } } } },
})

function mountOverlay(props: Record<string, unknown>) {
  return mount(PreviewLoadingOverlay, {
    props: { percent: 0, streamActive: false, streamLabel: null, ...props },
    global: { plugins: [i18n] },
  })
}

describe('PreviewLoadingOverlay', () => {
  it('shows the percent and fills the progress bar to match', () => {
    const wrapper = mountOverlay({ percent: 42 })
    expect(wrapper.find('[data-test="modal-v2-preview-percent"]').text()).toContain('42')
    const bar = wrapper.find('[data-test="modal-v2-preview-progress"]')
    expect(bar.attributes('aria-valuenow')).toBe('42')
    expect(wrapper.find('.preview-overlay__bar-fill').attributes('style')).toContain('width: 42%')
  })

  it('shows the stream layer label only when the stream is active', async () => {
    const wrapper = mountOverlay({ streamActive: false, streamLabel: 'Layer 2/5' })
    expect(wrapper.find('.preview-overlay__layer').exists()).toBe(false)
    await wrapper.setProps({ streamActive: true })
    expect(wrapper.find('.preview-overlay__layer').text()).toContain('Layer 2/5')
  })
})
