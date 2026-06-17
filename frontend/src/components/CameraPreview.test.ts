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
    // happy-dom has no layout: stub the container rect + image natural size so
    // the source-pixel → screen mapping produces a box.
    const container = wrapper.find('[data-test="camera-preview"]').element
    container.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 200, height: 200, right: 200, bottom: 200, x: 0, y: 0 }) as DOMRect
    const img = wrapper.find('[data-test="preview-img"]')
    Object.defineProperty(img.element, 'naturalWidth', { value: 200, configurable: true })
    Object.defineProperty(img.element, 'naturalHeight', { value: 200, configurable: true })
    await img.trigger('load')
    await nextTick()
    expect(wrapper.find('[data-test="preview-roi"]').exists()).toBe(true)
  })

  it('emits update:roi when a zone is dragged in editable mode', async () => {
    const wrapper = mount(CameraPreview, {
      props: { url: 'http://cam/stream', editable: true },
      global: { plugins: [i18n] },
    })
    const container = wrapper.find('[data-test="camera-preview"]')
    container.element.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 200, height: 200, right: 200, bottom: 200, x: 0, y: 0 }) as DOMRect
    const img = wrapper.find('[data-test="preview-img"]')
    Object.defineProperty(img.element, 'naturalWidth', { value: 200, configurable: true })
    Object.defineProperty(img.element, 'naturalHeight', { value: 200, configurable: true })
    await img.trigger('load')
    await nextTick()

    // 200px container, 200px image → scale 1, no letterbox: screen px == src px.
    await container.trigger('pointerdown', { clientX: 20, clientY: 30, pointerId: 1 })
    await container.trigger('pointermove', { clientX: 70, clientY: 90, pointerId: 1 })
    await container.trigger('pointerup', { pointerId: 1 })

    const evt = wrapper.emitted('update:roi')
    expect(evt).toBeTruthy()
    expect(evt![0]![0]).toEqual({ x: 20, y: 30, width: 50, height: 60 })
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
