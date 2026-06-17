// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import en from '../locales/en.json'
import CameraView from './CameraView.vue'
import { useUiStore, type CameraConfig } from '../stores/ui'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en },
})

// CameraView only mounts the stream <img> while the panel is in the
// viewport (useInViewport). happy-dom ships an IntersectionObserver that
// never fires, so stub one that reports the element on screen — otherwise
// `visible` would stay false and the feed would never render under test.
class MockIO {
  cb: (entries: Array<{ isIntersecting: boolean; target: Element }>, o: unknown) => void
  constructor(cb: MockIO['cb']) {
    this.cb = cb
  }
  observe(el: Element): void {
    this.cb([{ isIntersecting: true, target: el }], this)
  }
  disconnect(): void {}
  unobserve(): void {}
  takeRecords(): [] {
    return []
  }
}

function cam(over: Partial<CameraConfig> = {}): CameraConfig {
  return { enabled: false, url: '', label: '', ...over }
}

function mountView() {
  return mount(CameraView, { global: { plugins: [i18n] } })
}

describe('CameraView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('IntersectionObserver', MockIO)
    try {
      localStorage.clear()
    } catch {
      /* localStorage unavailable in this env — ignore */
    }
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows a configure hint that opens System settings when no camera is set', async () => {
    const ui = useUiStore()
    const wrapper = mountView()
    await nextTick()

    expect(wrapper.find('[data-test="camera-stream"]').exists()).toBe(false)
    const cta = wrapper.find('[data-test="camera-configure"]')
    expect(cta.exists()).toBe(true)

    await cta.trigger('click')
    expect(ui.settingsOpen).toBe(true)
    expect(ui.settingsTab).toBe('system')
  })

  it('renders a single live stream without a switcher', async () => {
    const ui = useUiStore()
    ui.cameras = [cam({ enabled: true, url: 'http://cam.local/stream' }), cam()]
    const wrapper = mountView()
    await nextTick()

    const img = wrapper.find('[data-test="camera-stream"]')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toBe('http://cam.local/stream')
    expect(wrapper.find('[data-test="camera-live"]').exists()).toBe(true)
    // Only one active camera → no switcher.
    expect(wrapper.find('[data-test="camera-switcher"]').exists()).toBe(false)
  })

  it('shows a switcher and switches between two active cameras', async () => {
    const ui = useUiStore()
    ui.cameras = [
      cam({ enabled: true, url: 'http://cam1/stream', label: 'Top' }),
      cam({ enabled: true, url: 'http://cam2/stream', label: 'Side' }),
    ]
    const wrapper = mountView()
    await nextTick()

    expect(wrapper.find('[data-test="camera-switcher"]').exists()).toBe(true)
    // First active camera shown by default.
    expect(wrapper.find('[data-test="camera-stream"]').attributes('src')).toBe('http://cam1/stream')

    await wrapper.find('[data-test="camera-select-1"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="camera-stream"]').attributes('src')).toBe('http://cam2/stream')
  })

  it('stays in the configure state when enabled but the URL is blank', async () => {
    const ui = useUiStore()
    ui.cameras = [cam({ enabled: true, url: '   ' }), cam()]
    const wrapper = mountView()
    await nextTick()

    expect(wrapper.find('[data-test="camera-stream"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="camera-configure"]').exists()).toBe(true)
  })

  it('shows an error state when the stream fails to load', async () => {
    const ui = useUiStore()
    ui.cameras = [cam({ enabled: true, url: 'http://cam.local/stream' }), cam()]
    const wrapper = mountView()
    await nextTick()

    await wrapper.find('[data-test="camera-stream"]').trigger('error')
    await nextTick()

    expect(wrapper.find('[data-test="camera-stream"]').exists()).toBe(false)
    expect(wrapper.text()).toContain(en.camera.streamError)
  })
})
