// @vitest-environment happy-dom
import { describe, expect, it, beforeEach } from 'vitest'
import { ref } from 'vue'
import type { Placement } from '../../stores/job'
import { hydrateScene, persistScene, type ScenePersistenceRefs } from './sceneStorage'

function emptyPlacement(overrides: Partial<Placement> = {}): Placement {
  return {
    id: 'p1',
    library_file_id: null,
    source_file: '',
    source_mime: '',
    job_id: null,
    rerenderable: false,
    svg: '',
    layers: [],
    source_bbox: { x_min: 0, y_min: 0, x_max: 0, y_max: 0 },
    layer_algorithms: {},
    upload_warnings: [],
    upload_metadata: {},
    last_file: null,
    last_options: undefined,
    visibility: {},
    x_mm: 0,
    y_mm: 0,
    width_mm: 100,
    height_mm: 100,
    rotation: 0,
    flip_h: false,
    flip_v: false,
    ...overrides,
  }
}

function makeRefs(): ScenePersistenceRefs {
  return {
    placements: ref<Placement[]>([]),
    selectedPlacementId: ref<string | null>(null),
    selectedProfileName: ref('Test'),
    scaleMode: ref<'fit' | 'actual'>('fit'),
    marginMm: ref(10),
    autoOptimize: ref(true),
  }
}

describe('sceneStorage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('round-trips a scene through localStorage', () => {
    const out = makeRefs()
    out.placements.value = [emptyPlacement({ id: 'abc', source_file: 'logo.svg' })]
    out.selectedPlacementId.value = 'abc'
    out.selectedProfileName.value = 'My profile'
    out.scaleMode.value = 'actual'
    out.marginMm.value = 0
    out.autoOptimize.value = false
    persistScene(out)

    const restored = makeRefs()
    hydrateScene(restored)
    expect(restored.placements.value).toHaveLength(1)
    expect(restored.placements.value[0]!.source_file).toBe('logo.svg')
    expect(restored.selectedPlacementId.value).toBe('abc')
    expect(restored.selectedProfileName.value).toBe('My profile')
    expect(restored.scaleMode.value).toBe('actual')
    expect(restored.marginMm.value).toBe(0)
    expect(restored.autoOptimize.value).toBe(false)
  })

  it('migrates a legacy v3 scene to v5 and removes the old key', () => {
    // Pre-v4 placements lack ``library_file_id`` and ``rotation``;
    // ``hydrateScene`` should default them rather than crash, and
    // delete the v3 key once migrated.
    const legacy = {
      placements: [
        {
          id: 'legacy',
          source_file: 'old.svg',
          source_mime: 'image/svg+xml',
          job_id: null,
          svg: '',
          layers: [],
          source_bbox: { x_min: 0, y_min: 0, x_max: 0, y_max: 0 },
          layer_algorithms: {},
          upload_warnings: [],
          upload_metadata: {},
          last_options: undefined,
          visibility: {},
          x_mm: 0,
          y_mm: 0,
          width_mm: 10,
          height_mm: 10,
        },
      ],
      selectedPlacementId: 'legacy',
      selectedProfileName: 'P',
      scaleMode: 'fit',
      marginMm: 5,
      autoOptimize: true,
    }
    localStorage.setItem('omniplot.scene.v3', JSON.stringify(legacy))

    const refs = makeRefs()
    const migrated = hydrateScene(refs)
    expect(migrated).toBe(true)
    expect(refs.placements.value).toHaveLength(1)
    const p = refs.placements.value[0]!
    expect(p.library_file_id).toBeNull()
    expect(p.rotation).toBe(0)
    // No more variants wrapper — pre-v4 placements arrive with empty
    // layer_algorithms and the migration defaults the per-layer maps.
    expect(p.layer_algorithms).toEqual({})
    expect(p.visibility).toEqual({})
    expect(localStorage.getItem('omniplot.scene.v3')).toBeNull()
    expect(localStorage.getItem('omniplot.scene.v5')).not.toBeNull()
  })

  it('migrates a v4 scene by collapsing the active variant into the placement', () => {
    // v4 stored ``variants`` + ``active_variant_id`` on the placement;
    // v5 flattens to a single style per file so the migration has to
    // promote the active variant's layer state onto the placement and
    // drop the wrapper.
    const v4 = {
      placements: [
        {
          id: 'p-v4',
          library_file_id: 'lib-1',
          source_file: 'a.png',
          source_mime: 'image/png',
          job_id: 'lib-1',
          rerenderable: true,
          svg: '<svg/>',
          layers: [],
          source_bbox: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 },
          layer_algorithms: {},
          upload_warnings: [],
          upload_metadata: {},
          last_options: undefined,
          visibility: {},
          x_mm: 0,
          y_mm: 0,
          width_mm: 10,
          height_mm: 10,
          rotation: 0,
          flip_h: false,
          flip_v: false,
          variants: [
            { id: 'v1', name: 'default', layer_algorithms: {}, visibility: {} },
            {
              id: 'v2',
              name: 'sketch',
              layer_algorithms: { L1: { algorithm: 'pencil', algorithm_options: {} } },
              visibility: { L1: false },
            },
          ],
          active_variant_id: 'v2',
        },
      ],
      selectedPlacementId: 'p-v4',
      selectedProfileName: 'P',
      scaleMode: 'fit',
      marginMm: 5,
      autoOptimize: true,
    }
    localStorage.setItem('omniplot.scene.v4', JSON.stringify(v4))

    const refs = makeRefs()
    const migrated = hydrateScene(refs)
    expect(migrated).toBe(true)
    const p = refs.placements.value[0]! as Placement & {
      variants?: unknown
      active_variant_id?: unknown
    }
    expect(p.layer_algorithms).toEqual({ L1: { algorithm: 'pencil', algorithm_options: {} } })
    expect(p.visibility).toEqual({ L1: false })
    expect(p.variants).toBeUndefined()
    expect(p.active_variant_id).toBeUndefined()
    expect(localStorage.getItem('omniplot.scene.v4')).toBeNull()
  })

  it('returns false (and leaves refs untouched) when no scene is stored', () => {
    const refs = makeRefs()
    refs.selectedProfileName.value = 'untouched'
    const migrated = hydrateScene(refs)
    expect(migrated).toBe(false)
    expect(refs.selectedProfileName.value).toBe('untouched')
  })
})
