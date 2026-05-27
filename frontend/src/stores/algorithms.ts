// Algorithms catalog store (roadmap B.4).
//
// Wraps the versioned /manifests/algorithms endpoint with cache +
// snapshot fallback (see src/domain/manifests/client.ts) so the rest
// of the UI consumes algorithm metadata from a single, reactive source
// of truth instead of hitting /algorithms directly. The legacy
// AlgorithmInfo[] shape is exposed via a derived getter so existing
// call sites (EditPreviewPane, useLayerCardState) can switch over with
// a one-line import change.
//
// A new algorithm registered in the backend manifest becomes usable in
// the frontend the moment this store refreshes — no TS type to patch,
// no constant to add, no rebuild required.

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { AlgorithmComplexity, AlgorithmInfo, AlgorithmKind } from '../api/client'
import {
  fetchAlgorithmsManifest,
  type ManifestSource,
} from '../domain/manifests/client'
import type { AlgorithmManifestEntry } from '../domain/manifests/schemas'

export const useAlgorithmsStore = defineStore('algorithms', () => {
  const entries = ref<AlgorithmManifestEntry[]>([])
  const manifestVersion = ref<number | null>(null)
  const source = ref<ManifestSource | null>(null)
  const lastError = ref<Error | null>(null)
  const loading = ref(false)
  // ``loaded`` flips after the first successful refresh — UIs can use
  // it to distinguish "no algorithms" (impossible in practice) from
  // "not fetched yet".
  const loaded = ref(false)

  // Legacy shape — drop-in replacement for ``getAlgorithms()`` callers.
  const list = computed<AlgorithmInfo[]>(() =>
    entries.value.map((e) => ({
      name: e.name,
      description: e.description,
      kind: e.kind as AlgorithmKind,
      complexity: e.complexity as AlgorithmComplexity,
    })),
  )

  const byId = computed<Map<string, AlgorithmManifestEntry>>(
    () => new Map(entries.value.map((e) => [e.id, e])),
  )

  // True when the catalog is being served from a stale source (cache
  // or build-time snapshot) — surfaced by ``ManifestFallbackBanner``.
  const fromFallback = computed(() => source.value !== null && source.value !== 'live')

  async function refresh(): Promise<void> {
    loading.value = true
    try {
      const result = await fetchAlgorithmsManifest()
      entries.value = result.data.entries
      manifestVersion.value = result.data.meta.manifest_version
      source.value = result.source
      lastError.value = result.error ?? null
      loaded.value = true
    } finally {
      loading.value = false
    }
  }

  return {
    entries,
    list,
    byId,
    manifestVersion,
    source,
    fromFallback,
    lastError,
    loading,
    loaded,
    refresh,
  }
})
