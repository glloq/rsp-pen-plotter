// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Partial mock: keep the real client but intercept the /rerender call so
// we can assert the payload the pass helpers build without a backend.
const rerenderJob = vi.fn()
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, rerenderJob: (...args: unknown[]) => rerenderJob(...args) }
})

import { useJobStore, type LayerPass, type Placement } from './job'
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
    layers: [makeLayer({ layer_id: 'a' }), makeLayer({ layer_id: 'b' })],
    source_bbox: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 },
    layer_algorithms: {},
    upload_warnings: [],
    upload_metadata: {},
    last_file: null,
    last_options: undefined,
    visibility: {},
    variants: [],
    active_variant_id: '',
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

const PASSES: LayerPass[] = [
  { algorithm: 'crosshatch', algorithm_options: { spacing_px: 3, angle_deg: 45, crossed: true } },
  { algorithm: 'crosshatch', algorithm_options: { spacing_px: 3, angle_deg: 15, crossed: true } },
]

describe('multi-pass helpers', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    rerenderJob.mockReset()
  })

  it('previewPassesOnAllLayers renders the stack on every layer without mutating state', async () => {
    rerenderJob.mockResolvedValue({ svg: '<svg id="rendered"/>', warnings: [] })
    const store = useJobStore()
    store.placements = [makePlacement()]
    store.selectPlacement('p1')

    const result = await store.previewPassesOnAllLayers(PASSES)

    expect(result?.svg).toBe('<svg id="rendered"/>')
    // Payload: every layer carries the full ordered pass stack.
    const [, layersPayload] = rerenderJob.mock.calls[0]!
    expect(layersPayload).toHaveLength(2)
    expect(layersPayload[0].layer_id).toBe('a')
    expect(layersPayload[0].passes).toHaveLength(2)
    expect(layersPayload[0].passes[1].algorithm_options.angle_deg).toBe(15)
    // Non-destructive: live placement state is untouched.
    expect(store.placements[0]!.layer_algorithms).toEqual({})
  })

  it('previewPassesOnAllLayers returns null when nothing is renderable', async () => {
    const store = useJobStore()
    store.placements = [makePlacement({ rerenderable: false })]
    store.selectPlacement('p1')
    expect(await store.previewPassesOnAllLayers(PASSES)).toBeNull()
    expect(rerenderJob).not.toHaveBeenCalled()
  })

  it('applyPassesToAllLayers writes the pass stack to every layer', async () => {
    const store = useJobStore()
    store.placements = [makePlacement()]
    store.selectPlacement('p1')

    await store.applyPassesToAllLayers(PASSES)

    const algos = store.placements[0]!.layer_algorithms
    expect(Object.keys(algos)).toEqual(['a', 'b'])
    // First pass mirrored into the legacy fields; full stack in passes.
    expect(algos.a!.algorithm).toBe('crosshatch')
    expect(algos.a!.algorithm_options.angle_deg).toBe(45)
    expect(algos.a!.passes).toHaveLength(2)
    expect(algos.b!.passes![1]!.algorithm_options.angle_deg).toBe(15)
  })
})
