// Scene persistence: read/write the editor state to ``localStorage``
// so a tab refresh keeps the operator's placements, profile and
// settings intact. Lifted out of ``stores/job.ts`` so the store
// itself only handles state — the (de)serialisation and the v2/v3
// migration live here.

import type { Ref } from 'vue'
import { watch } from 'vue'
import type { Placement, Variant } from '../../stores/job'

const SCENE_KEY = 'omniplot.scene.v4'
const LEGACY_SCENE_KEYS = ['omniplot.scene.v3', 'omniplot.scene.v2']

export interface SerializableScene {
  placements: Placement[]
  selectedPlacementId: string | null
  selectedProfileName: string
  scaleMode: 'fit' | 'actual'
  marginMm: number
  autoOptimize: boolean
}

export interface ScenePersistenceRefs {
  placements: Ref<Placement[]>
  selectedPlacementId: Ref<string | null>
  selectedProfileName: Ref<string>
  scaleMode: Ref<'fit' | 'actual'>
  marginMm: Ref<number>
  autoOptimize: Ref<boolean>
  /** Build a default variant for placements migrated from a pre-v3 scene. */
  makeDefaultVariant: () => Variant
}

/** Serialise the live editor state to a JSON string for ``localStorage``. */
export function serializeScene(refs: ScenePersistenceRefs): string {
  const data: SerializableScene = {
    // ``last_file`` is a File handle — can't survive JSON.
    placements: refs.placements.value.map((p) => ({ ...p, last_file: null })),
    selectedPlacementId: refs.selectedPlacementId.value,
    selectedProfileName: refs.selectedProfileName.value,
    scaleMode: refs.scaleMode.value,
    marginMm: refs.marginMm.value,
    autoOptimize: refs.autoOptimize.value,
  }
  return JSON.stringify(data)
}

/** Write the current scene to localStorage, swallowing quota/private-mode errors. */
export function persistScene(refs: ScenePersistenceRefs): void {
  try {
    localStorage.setItem(SCENE_KEY, serializeScene(refs))
  } catch {
    // localStorage may be unavailable (private browsing) or full.
  }
}

/**
 * Load the scene from localStorage and apply it to the refs.
 *
 * Returns ``true`` when a migration from a legacy key happened — the
 * caller should re-persist immediately so the v4 entry is created
 * and the legacy keys can be deleted.
 */
export function hydrateScene(refs: ScenePersistenceRefs): boolean {
  try {
    let raw = localStorage.getItem(SCENE_KEY)
    let migrating = false
    if (!raw) {
      for (const legacy of LEGACY_SCENE_KEYS) {
        const legacyRaw = localStorage.getItem(legacy)
        if (legacyRaw) {
          raw = legacyRaw
          migrating = true
          break
        }
      }
      if (!raw) return false
    }
    const data = JSON.parse(raw) as Partial<SerializableScene>
    if (Array.isArray(data.placements)) {
      refs.placements.value = data.placements.map((p) =>
        migrateLegacyPlacement(p, refs.makeDefaultVariant),
      )
    }
    if (data.selectedPlacementId !== undefined) {
      refs.selectedPlacementId.value = data.selectedPlacementId
    }
    if (data.selectedProfileName) refs.selectedProfileName.value = data.selectedProfileName
    if (data.scaleMode) refs.scaleMode.value = data.scaleMode
    if (typeof data.marginMm === 'number') refs.marginMm.value = data.marginMm
    if (typeof data.autoOptimize === 'boolean') refs.autoOptimize.value = data.autoOptimize
    if (migrating) {
      for (const legacy of LEGACY_SCENE_KEYS) localStorage.removeItem(legacy)
      persistScene(refs)
    }
    return migrating
  } catch {
    // Malformed JSON / no localStorage — start fresh.
    return false
  }
}

/**
 * Hydrate immediately, then auto-persist on changes (300 ms debounce).
 *
 * Returns a teardown function for tests that need to detach the watch.
 */
export function attachScenePersistence(refs: ScenePersistenceRefs): () => void {
  hydrateScene(refs)
  let timer: ReturnType<typeof setTimeout> | null = null
  const stop = watch(
    [
      refs.placements,
      refs.selectedPlacementId,
      refs.selectedProfileName,
      refs.scaleMode,
      refs.marginMm,
      refs.autoOptimize,
    ],
    () => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => persistScene(refs), 300)
    },
    { deep: true },
  )
  return () => {
    stop()
    if (timer) clearTimeout(timer)
  }
}

function migrateLegacyPlacement(
  p: Partial<Placement>,
  makeDefaultVariant: () => Variant,
): Placement {
  // Default the fields that pre-v4 scenes didn't carry.
  const placement = {
    ...({
      library_file_id: null,
      rerenderable: false,
      rotation: 0,
      flip_h: false,
      flip_v: false,
    } as Pick<Placement, 'library_file_id' | 'rerenderable' | 'rotation' | 'flip_h' | 'flip_v'>),
    ...p,
    last_file: null,
  } as Placement
  // v2 → v3 migration: wrap legacy placement state in a default
  // variant so the variant API has a snapshot to point at.
  if (!Array.isArray(placement.variants) || !placement.variants.length) {
    const variant = makeDefaultVariant()
    variant.layer_algorithms = { ...(placement.layer_algorithms ?? {}) }
    variant.visibility = { ...(placement.visibility ?? {}) }
    placement.variants = [variant]
    placement.active_variant_id = variant.id
  }
  return placement
}
