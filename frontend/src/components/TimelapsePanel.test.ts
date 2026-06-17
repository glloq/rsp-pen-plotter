// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { TimelapseStatus, TimelapseSummary } from '../api/client'

const IDLE: TimelapseStatus = {
  recording: false,
  session_id: null,
  label: '',
  frame_count: 0,
  interval_seconds: 0,
  fps: 0,
  started_at: null,
  error: null,
}

const h = vi.hoisted(() => ({
  getTimelapseStatus: vi.fn(),
  startTimelapse: vi.fn(),
  stopTimelapse: vi.fn(),
  listTimelapses: vi.fn(),
  deleteTimelapse: vi.fn(),
  downloadTimelapseVideo: vi.fn(),
}))

vi.mock('../api/client', async (orig) => {
  const actual = await orig<typeof import('../api/client')>()
  return { ...actual, ...h }
})
vi.mock('../composables/confirm', () => ({ confirmAction: vi.fn(async () => true) }))

import en from '../locales/en.json'
import TimelapsePanel from './TimelapsePanel.vue'
import { useUiStore, type CameraConfig } from '../stores/ui'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en },
})

function cam(over: Partial<CameraConfig> = {}): CameraConfig {
  return { enabled: false, url: '', label: '', ...over }
}

function summary(over: Partial<TimelapseSummary> = {}): TimelapseSummary {
  return {
    id: 't1',
    label: 'spiral',
    created_at: '2026-01-01T00:00:00Z',
    interval_seconds: 5,
    fps: 24,
    frame_count: 120,
    duration_seconds: 5,
    has_video: true,
    size_bytes: 1024 * 1024,
    ...over,
  }
}

function mountPanel() {
  return mount(TimelapsePanel, { global: { plugins: [i18n] } })
}

describe('TimelapsePanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useUiStore().canvasTab = 'plotter'
    h.getTimelapseStatus.mockReset().mockResolvedValue({ ...IDLE })
    h.startTimelapse.mockReset().mockResolvedValue({ ...IDLE, recording: true })
    h.stopTimelapse.mockReset().mockResolvedValue(summary())
    h.listTimelapses.mockReset().mockResolvedValue([])
    h.deleteTimelapse.mockReset().mockResolvedValue(undefined)
    h.downloadTimelapseVideo.mockReset().mockResolvedValue(new Blob(['x']))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('is collapsed by default and prompts to configure a camera', async () => {
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.find('[data-test="timelapse-toggle"]').attributes('aria-expanded')).toBe('false')
    await wrapper.find('[data-test="timelapse-toggle"]').trigger('click')
    await flushPromises()
    // No camera configured → hint, no start control.
    expect(wrapper.find('[data-test="timelapse-no-camera"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="timelapse-start"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('starts a recording from the selected camera', async () => {
    useUiStore().cameras = [cam({ enabled: true, url: 'http://cam/stream', label: 'Top' }), cam()]
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.find('[data-test="timelapse-toggle"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="timelapse-start"]').trigger('click')
    await flushPromises()

    expect(h.startTimelapse).toHaveBeenCalledWith('http://cam/stream', 5, 24, '')
    wrapper.unmount()
  })

  it('shows stop while recording and stops on click', async () => {
    h.getTimelapseStatus.mockResolvedValue({
      ...IDLE,
      recording: true,
      frame_count: 7,
      session_id: 's1',
    })
    useUiStore().cameras = [cam({ enabled: true, url: 'http://cam/stream' }), cam()]
    const wrapper = mountPanel()
    await flushPromises()

    // Live REC indicator in the (collapsed) header.
    expect(wrapper.find('[data-test="timelapse-rec"]').exists()).toBe(true)
    await wrapper.find('[data-test="timelapse-toggle"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="timelapse-stop"]').trigger('click')
    await flushPromises()

    expect(h.stopTimelapse).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('lists saved timelapses and downloads one', async () => {
    h.listTimelapses.mockResolvedValue([summary({ id: 't9', label: 'demo' })])
    // The store triggers the download via a temporary <a>.click(); stub it
    // so happy-dom doesn't try to navigate on the object-URL.
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.find('[data-test="timelapse-toggle"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="timelapse-file-t9"]').exists()).toBe(true)

    await wrapper.find('[data-test="timelapse-download-t9"]').trigger('click')
    await flushPromises()
    expect(h.downloadTimelapseVideo).toHaveBeenCalledWith('t9')

    clickSpy.mockRestore()
    wrapper.unmount()
  })
})
