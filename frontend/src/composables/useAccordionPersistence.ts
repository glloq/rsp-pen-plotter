// Persisted "is this card expanded?" state, keyed per card. The editor
// has half a dozen accordion cards (Segmentation, PostProcess,
// Typography, Background, …) that each owned a ``ref(true/false)``
// locally — so reopening the modal always reset every collapsed
// card back to its default, even when the operator had just spent
// time deciding which one they wanted to focus on.
//
// This composable replaces the local refs with a persisted one keyed
// by ``cardKey``. Stale keys older than ~30 days are garbage-collected
// at boot so localStorage doesn't accumulate forgotten cards.

import { ref, watch, type Ref } from 'vue'

const STORAGE_KEY = 'omniplot.editModal.accordion'
const GC_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000  // 30 days

interface PersistedEntry {
  expanded: boolean
  ts: number
}

let _cache: Record<string, PersistedEntry> | null = null

function loadCache(): Record<string, PersistedEntry> {
  if (_cache) return _cache
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Record<string, PersistedEntry>
      const now = Date.now()
      // Drop stale keys at load time so the file never grows unboundedly.
      const fresh: Record<string, PersistedEntry> = {}
      for (const [k, v] of Object.entries(parsed)) {
        if (v && typeof v === 'object' && now - (v.ts ?? 0) < GC_MAX_AGE_MS) {
          fresh[k] = v
        }
      }
      _cache = fresh
      return fresh
    }
  } catch {
    // localStorage unavailable or corrupt — fall through to empty.
  }
  _cache = {}
  return _cache
}

function persist(): void {
  if (!_cache) return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(_cache))
  } catch {
    // Quota / unavailable — non-fatal, the in-memory cache still works
    // for the current session.
  }
}

export function useAccordionPersistence(cardKey: string, defaultExpanded = true): Ref<boolean> {
  const cache = loadCache()
  const initial = cache[cardKey]?.expanded ?? defaultExpanded
  const expanded = ref<boolean>(initial)

  watch(expanded, (v) => {
    cache[cardKey] = { expanded: v, ts: Date.now() }
    persist()
  })

  return expanded
}
