// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useJobStore, type Placement } from './job'
import { useEditState } from '../composables/useEditState'
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
    id: `p${Math.random().toString(36).slice(2)}`,
    library_file_id: null,
    source_file: 'x.png',
    source_mime: 'image/png',
    job_id: null,
    rerenderable: false,
    svg: '<svg/>',
    layers: [makeLayer()],
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

describe('resnapAutoLayers', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('snaps auto layers to the nearest pool hex and leaves manual overrides', () => {
    const store = useJobStore()
    store.placements = [
      makePlacement({
        layers: [
          makeLayer({ layer_id: 'a', source_color: '#fe0000', color_assignment: 'auto' }),
          makeLayer({
            layer_id: 'b',
            source_color: '#0000ee',
            color_assignment: 'manual',
            assigned_color_hex: '#123456',
          }),
        ],
      }),
    ]

    store.resnapAutoLayers(['#ff0000', '#00ff00'])

    const layers = store.placements[0]!.layers
    expect(layers[0]!.assigned_color_hex).toBe('#ff0000')
    expect(layers[0]!.color_assignment).toBe('auto')
    // Manual override is preserved verbatim.
    expect(layers[1]!.assigned_color_hex).toBe('#123456')
    expect(layers[1]!.color_assignment).toBe('manual')
  })

  it('clears the auto assignment when the pool is empty', () => {
    const store = useJobStore()
    store.placements = [
      makePlacement({
        layers: [makeLayer({ source_color: '#abcdef', assigned_color_hex: '#abcdef' })],
      }),
    ]

    store.resnapAutoLayers([])

    expect(store.placements[0]!.layers[0]!.assigned_color_hex).toBeNull()
  })

  it('keeps faithful centroids for image-colours placements (kmeans, no ink_pool)', () => {
    // "Fidèle à l'image": a placement converted with kmeans and WITHOUT an
    // ink_pool means the operator chose to render the photo's own colours.
    // resnap must not snap those onto the pool, even though a pool exists —
    // it clears the auto assignment so the layer renders its centroid.
    const store = useJobStore()
    store.placements = [
      makePlacement({
        last_options: { segmentation_method: 'kmeans' },
        layers: [
          makeLayer({ layer_id: 'a', source_color: '#5a6b3c', assigned_color_hex: '#ff0000' }),
        ],
      }),
    ]

    store.resnapAutoLayers(['#ff0000', '#00ff00', '#0000ff'])

    expect(store.placements[0]!.layers[0]!.assigned_color_hex).toBeNull()
  })

  it('still snaps pens-follow placements (kmeans_lab WITH ink_pool)', () => {
    // The follow-pens path always ships an ink_pool — it must keep snapping
    // onto the rack so every owned pen shows up.
    const store = useJobStore()
    store.placements = [
      makePlacement({
        last_options: { segmentation_method: 'kmeans_lab', ink_pool: ['#ff0000', '#00ff00'] },
        layers: [makeLayer({ source_color: '#10ff00' })],
      }),
    ]

    store.resnapAutoLayers(['#ff0000', '#00ff00'])

    expect(store.placements[0]!.layers[0]!.assigned_color_hex).toBe('#00ff00')
  })

  it('re-snaps across all placements', () => {
    const store = useJobStore()
    store.placements = [
      makePlacement({ layers: [makeLayer({ source_color: '#10ff00' })] }),
      makePlacement({ layers: [makeLayer({ source_color: '#ff1000' })] }),
    ]

    store.resnapAutoLayers(['#ff0000', '#00ff00'])

    expect(store.placements[0]!.layers[0]!.assigned_color_hex).toBe('#00ff00')
    expect(store.placements[1]!.layers[0]!.assigned_color_hex).toBe('#ff0000')
  })
})

describe('updateLayer ink change → preview wash-out', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('clears the live preview SVG when a layer ink changes', () => {
    // The live /preview SVG ignores per-layer ink assignments and has
    // display priority in the editor, so a stale one would mask the
    // recoloured /rerender result (expert mode showed no change).
    const store = useJobStore()
    const placement = makePlacement()
    store.placements = [placement]
    store.selectPlacement(placement.id)
    useEditState().previewSvg.value = '<svg>stale</svg>'

    store.updateLayer('layer-1', { assigned_color_hex: '#ff0000' })

    expect(store.placements[0]!.layers[0]!.assigned_color_hex).toBe('#ff0000')
    expect(useEditState().previewSvg.value).toBe('')
  })

  it('leaves the live preview SVG alone for non-colour patches', () => {
    const store = useJobStore()
    const placement = makePlacement()
    store.placements = [placement]
    store.selectPlacement(placement.id)
    useEditState().previewSvg.value = '<svg>live</svg>'

    store.updateLayer('layer-1', { target_pen_slot: 2 })

    expect(useEditState().previewSvg.value).toBe('<svg>live</svg>')
  })
})

describe('removePlacementsForFile (ghost-image cleanup)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('drops every placement (visible or draft) backed by the deleted file', () => {
    const store = useJobStore()
    store.placements = [
      makePlacement({ library_file_id: 'file-A' }),
      makePlacement({ library_file_id: 'file-A', is_library_draft: true }),
      makePlacement({ library_file_id: 'file-B' }),
    ]

    store.removePlacementsForFile('file-A')

    expect(store.placements).toHaveLength(1)
    expect(store.placements[0]!.library_file_id).toBe('file-B')
  })

  it('is a no-op when no placement references the file', () => {
    const store = useJobStore()
    store.placements = [makePlacement({ library_file_id: 'file-B' })]
    store.removePlacementsForFile('file-A')
    expect(store.placements).toHaveLength(1)
  })

  it('reselects a remaining visible placement when the selected one is removed', () => {
    const store = useJobStore()
    const keep = makePlacement({ library_file_id: 'file-B' })
    const drop = makePlacement({ library_file_id: 'file-A' })
    store.placements = [drop, keep]
    store.selectPlacement(drop.id)

    store.removePlacementsForFile('file-A')

    expect(store.selectedPlacementId).toBe(keep.id)
  })
})
