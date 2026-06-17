// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import CameraPreview from './CameraPreview.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      camera: { title: 'Camera', live: 'Live', streamError: 'Video stream unavailable' },
      cameraPreview: { empty: 'No camera URL yet', retry: 'Retry', refresh: 'Refresh' },
    },
  },
})

function mountPreview(url: string) {
  return mount(CameraPreview, { props: { url }, global: { plugins: [i18n] } })
}

describe('CameraPreview', () => {
  it('shows the empty state without a URL', () => {
    const wrapper = mountPreview('   ')
    expect(wrapper.find('[data-test="preview-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="preview-img"]').exists()).toBe(false)
  })

  it('renders the stream and a live badge for a URL', () => {
    const wrapper = mountPreview('http://cam/stream')
    const img = wrapper.find('[data-test="preview-img"]')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toBe('http://cam/stream')
    expect(wrapper.find('[data-test="preview-live"]').exists()).toBe(true)
  })

  it('overlays the detection zone when a ROI is set', async () => {
    const wrapper = mount(CameraPreview, {
      props: { url: 'http://cam/stream', roi: { x: 10, y: 10, width: 40, height: 40 } },
      global: { plugins: [i18n] },
    })
    const img = wrapper.find('[data-test="preview-img"]')
    // happy-dom reports 0 natural dimensions; stub them so the overlay maps.
    Object.defineProperty(img.element, 'naturalWidth', { value: 200, configurable: true })
    Object.defineProperty(img.element, 'naturalHeight', { value: 200, configurable: true })
    await img.trigger('load')
    await nextTick()
    expect(wrapper.find('[data-test="preview-roi"]').exists()).toBe(true)
  })

  it('falls back to an error state and recovers on retry', async () => {
    const wrapper = mountPreview('http://cam/stream')
    await wrapper.find('[data-test="preview-img"]').trigger('error')
    await nextTick()
    expect(wrapper.find('[data-test="preview-error"]').exists()).toBe(true)

    await wrapper.find('[data-test="preview-retry"]').trigger('click')
    await nextTick()
    // Retry clears the error and cache-busts the src.
    const img = wrapper.find('[data-test="preview-img"]')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toContain('http://cam/stream')
    expect(img.attributes('src')).toContain('_op=')
  })
})
