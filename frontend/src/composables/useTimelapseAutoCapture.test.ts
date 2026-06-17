// @vitest-environment happy-dom
import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, type EffectScope } from 'vue'
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
  startTimelapse: vi.fn(),
  stopTimelapse: vi.fn(),
  getTimelapseStatus: vi.fn(),
  listTimelapses: vi.fn(),
}))

vi.mock('../api/client', async (orig) => {
  const actual = await orig<typeof import('../api/client')>()
  return { ...actual, ...h }
})

import { resolveCameraUrl, useTimelapseAutoCapture } from './useTimelapseAutoCapture'
import { usePlotterStore } from '../stores/plotter'
import { useTimelapseStore } from '../stores/timelapse'
import { useUiStore, type CameraConfig } from '../stores/ui'

function cam(over: Partial<CameraConfig> = {}): CameraConfig {
  return { enabled: false, url: '', label: '', ...over }
}

async function settle(): Promise<void> {
  await nextTick()
  await flushPromises()
}

describe('resolveCameraUrl', () => {
  it('uses the chosen slot, else the first configured camera, else empty', () => {
    const cams = [cam({ enabled: true, url: 'http://a' }), cam({ enabled: true, url: 'http://b' })]
    expect(resolveCameraUrl(cams, 1)).toBe('http://b')
    // Chosen slot not configured → first active.
    expect(resolveCameraUrl([cam(), cam({ enabled: true, url: 'http://b' })], 0)).toBe('http://b')
    // None configured.
    expect(resolveCameraUrl([cam(), cam()], 0)).toBe('')
  })
})

describe('useTimelapseAutoCapture', () => {
  let scope: EffectScope | null = null

  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    h.startTimelapse.mockReset().mockResolvedValue({ ...IDLE, recording: true })
    h.stopTimelapse.mockReset().mockResolvedValue({
      id: 't1',
      label: '',
      created_at: '',
      interval_seconds: 5,
      fps: 24,
      frame_count: 1,
      duration_seconds: 0,
      has_video: true,
      size_bytes: 1,
    } as TimelapseSummary)
    h.getTimelapseStatus.mockReset().mockResolvedValue({ ...IDLE })
    h.listTimelapses.mockReset().mockResolvedValue([])
  })

  afterEach(() => {
    scope?.stop()
    scope = null
  })

  it('auto-starts on print start and auto-stops on print end when enabled', async () => {
    const ui = useUiStore()
    ui.cameras = [cam({ enabled: true, url: 'http://cam/stream' }), cam()]
    useTimelapseStore().autoEnabled = true
    const plotter = usePlotterStore()

    scope = effectScope()
    scope.run(() => useTimelapseAutoCapture())

    // Print starts → auto-start.
    plotter.status.state = 'running'
    await settle()
    expect(h.startTimelapse).toHaveBeenCalledWith('http://cam/stream', 5, 24, 'print')

    // Print ends → auto-stop.
    plotter.status.state = 'done'
    await settle()
    expect(h.stopTimelapse).toHaveBeenCalled()
  })

  it('does nothing when auto-record is disabled', async () => {
    const ui = useUiStore()
    ui.cameras = [cam({ enabled: true, url: 'http://cam/stream' }), cam()]
    useTimelapseStore().autoEnabled = false
    const plotter = usePlotterStore()

    scope = effectScope()
    scope.run(() => useTimelapseAutoCapture())

    plotter.status.state = 'running'
    await settle()
    expect(h.startTimelapse).not.toHaveBeenCalled()
  })

  it('does not auto-stop a manually-started recording', async () => {
    const ui = useUiStore()
    ui.cameras = [cam({ enabled: true, url: 'http://cam/stream' }), cam()]
    const tl = useTimelapseStore()
    tl.autoEnabled = false
    // Simulate a manual recording already in progress.
    tl.status.recording = true
    const plotter = usePlotterStore()

    scope = effectScope()
    scope.run(() => useTimelapseAutoCapture())

    plotter.status.state = 'running'
    await settle()
    plotter.status.state = 'done'
    await settle()
    // Auto-capture never started it, so it must not stop it.
    expect(h.stopTimelapse).not.toHaveBeenCalled()
  })
})
