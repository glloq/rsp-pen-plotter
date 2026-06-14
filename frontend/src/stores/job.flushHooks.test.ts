// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Partial mock: keep the real client but intercept /rerender so the flush
// path can be asserted without a backend.
const rerenderJob = vi.fn()
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, rerenderJob: (...args: unknown[]) => rerenderJob(...args) }
})

import { useJobStore, type Placement } from './job'
import type { LayerInfo } from '../api/client'

function makeLayer(over: Partial<LayerInfo> = {}): LayerInfo {
  return {
    layer_id: 'layer-1',
    color_label: 'c',
    source_color: '#000000',
    assigned_color_hex: null,
    color_assignment: 'auto',
    target_pen_slot: 0,
    draw_order: 0,
    total_length_mm: 10,
    bbox: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 },
    ...over,
  } as LayerInfo
}

function makePlacement(over: Partial<Placement> = {}): Placement {
  return {
    id: 'p1',
    library_file_id: null,
    source_file: 'x.png',
    source_mime: 'image/png',
    job_id: 'job-1',
    rerenderable: true,
    svg: '<svg/>',
    layers: [makeLayer({ layer_id: 'a' })],
    source_bbox: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 },
    layer_algorithms: {},
    upload_warnings: [],
    upload_metadata: {},
    last_file: null,
    last_options: undefined,
    visibility: {},
    rotation: 0,
    flip_h: false,
    flip_v: false,
    x_mm: 0,
    y_mm: 0,
    width_mm: 10,
    height_mm: 10,
    ...over,
  } as Placement
}

beforeEach(() => {
  setActivePinia(createPinia())
  rerenderJob.mockReset()
})

describe('flushRerender pre-flush hooks', () => {
  it('drains a registered hook before reading placement.svg', async () => {
    rerenderJob.mockResolvedValue({ svg: '<svg id="flushed"/>', warnings: [] })
    const store = useJobStore()
    store.placements = [makePlacement()]
    store.selectPlacement('p1')

    // Simulate a component that debounced its layer_algorithms write
    // outside the store (the style-knob sliders): the propagation is
    // still pending when /generate flushes.
    let propagated = false
    const unregister = store.registerRerenderFlushHook(async () => {
      propagated = true
      await store.applyLayerAlgorithm('a', 'crosshatch', { spacing_px: 3 })
    })

    await store.flushRerender()

    expect(propagated).toBe(true)
    // The hook's layer_algorithms write must have reached the backend in
    // the same flush — not on a later, post-generate timer.
    expect(rerenderJob).toHaveBeenCalledTimes(1)
    const [, layersPayload] = rerenderJob.mock.calls.at(-1)!
    expect(layersPayload).toEqual([
      { layer_id: 'a', algorithm: 'crosshatch', algorithm_options: { spacing_px: 3 } },
    ])
    expect(store.placements[0]!.svg).toBe('<svg id="flushed"/>')

    unregister()
  })

  it('stops running a hook once it is unregistered', async () => {
    rerenderJob.mockResolvedValue({ svg: '<svg/>', warnings: [] })
    const store = useJobStore()
    store.placements = [makePlacement()]
    store.selectPlacement('p1')

    const hook = vi.fn()
    const unregister = store.registerRerenderFlushHook(hook)
    unregister()

    await store.flushRerender()
    expect(hook).not.toHaveBeenCalled()
  })

  it('a throwing hook does not stop the flush from completing', async () => {
    rerenderJob.mockResolvedValue({ svg: '<svg/>', warnings: [] })
    const store = useJobStore()
    store.placements = [makePlacement()]
    store.selectPlacement('p1')

    store.registerRerenderFlushHook(() => {
      throw new Error('propagation failed')
    })

    await expect(store.flushRerender()).resolves.toBeUndefined()
  })
})
