// Scene persistence: read/write the editor state to ``localStorage``
// so a tab refresh keeps the operator's placements, profile and
// settings intact. Lifted out of ``stores/job.ts`` so the store
// itself only handles state — the (de)serialisation and the v2/v3
// migration live here.

import type { Ref } from 'vue'
import { watch } from 'vue'
import type { Placement } from '../../stores/job'

const SCENE_KEY = 'omniplot.scene.v5'
// v4 stored ``placement.variants`` + ``active_variant_id``; the v0.2
// simplification flattened to a single style per file, so v4 entries
// are migrated by collapsing the active variant (or the first one)
// into the placement-level ``layer_algorithms`` + ``visibility`` and
// dropping the wrapper. v2/v3 keys still migrate via their original
// path inside ``migrateLegacyPlacement``.
const LEGACY_SCENE_KEYS = ['omniplot.scene.v4', 'omniplot.scene.v3', 'omniplot.scene.v2']

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
      refs.placements.value = data.placements.map((p) => migrateLegacyPlacement(p))
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

// Debounce window before a scene change is flushed to localStorage.
// Serialising the placements (SVGs included) + the synchronous
// ``setItem`` is the heaviest thing on the edit hot-path, so we both
// wait out bursts of edits (drag, slider scrub) and defer the actual
// write to an idle slot so it never blocks a frame.
const PERSIST_DEBOUNCE_MS = 600

type IdleCancel = () => void

// Run ``fn`` when the browser is idle, falling back to a macrotask where
// requestIdleCallback isn't available (Safari < 16, jsdom/happy-dom test
// envs). Returns a canceller so teardown can drop a pending write.
function runWhenIdle(fn: () => void): IdleCancel {
  const ric = (globalThis as { requestIdleCallback?: (cb: () => void) => number })
    .requestIdleCallback
  if (typeof ric === 'function') {
    const handle = ric(fn)
    const cancel = (globalThis as { cancelIdleCallback?: (h: number) => void }).cancelIdleCallback
    return () => cancel?.(handle)
  }
  const handle = setTimeout(fn, 0)
  return () => clearTimeout(handle)
}

/**
 * Hydrate immediately, then auto-persist on changes (debounced + idle).
 *
 * Returns a teardown function for tests that need to detach the watch.
 */
export function attachScenePersistence(refs: ScenePersistenceRefs): () => void {
  hydrateScene(refs)
  let timer: ReturnType<typeof setTimeout> | null = null
  let cancelIdle: IdleCancel | null = null
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
      timer = setTimeout(() => {
        cancelIdle?.()
        cancelIdle = runWhenIdle(() => persistScene(refs))
      }, PERSIST_DEBOUNCE_MS)
    },
    { deep: true },
  )
  return () => {
    stop()
    if (timer) clearTimeout(timer)
    cancelIdle?.()
  }
}

// Legacy variant snapshot shape — kept here so the v4→v5 migration
// can still read pre-flattening scenes without dragging the dead
// ``Variant`` interface into the store's public types.
interface LegacyVariantSnapshot {
  id: string
  name?: string
  layer_algorithms?: Record<string, unknown>
  visibility?: Record<string, boolean>
}

function migrateLegacyPlacement(p: Partial<Placement>): Placement {
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
  } as Placement & { variants?: LegacyVariantSnapshot[]; active_variant_id?: string }

  // v4 → v5: collapse the variants list down to the active snapshot's
  // ``layer_algorithms`` + ``visibility``, then drop the wrapper. Picks
  // the active variant by id, falling back to the first entry, so
  // older scenes with a missing/invalid ``active_variant_id`` still
  // produce a usable placement.
  if (Array.isArray(placement.variants) && placement.variants.length > 0) {
    const active =
      placement.variants.find((v) => v.id === placement.active_variant_id) ??
      placement.variants[0]!
    placement.layer_algorithms = {
      ...(placement.layer_algorithms ?? {}),
      ...(active.layer_algorithms ?? {}),
    } as Placement['layer_algorithms']
    placement.visibility = {
      ...(placement.visibility ?? {}),
      ...(active.visibility ?? {}),
    }
    delete placement.variants
    delete placement.active_variant_id
  }
  // Ensure the per-layer maps always exist — saves every consumer a
  // ``?? {}`` after the migration.
  if (!placement.layer_algorithms) placement.layer_algorithms = {}
  if (!placement.visibility) placement.visibility = {}
  return placement
}
