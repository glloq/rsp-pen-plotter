import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  deleteLibraryFile as apiDelete,
  getLibraryFile as apiGet,
  listLibraryFiles as apiList,
  listLibraryFolders as apiListFolders,
  patchLibraryFile as apiPatch,
  getFilesIntegrity,
  lookupLibraryFileByHash,
  sha256Hex,
  uploadToLibrary,
  type IntegrityIssue,
  type LibraryFileDetail,
  type LibraryFileRecord,
  type LibrarySortKey,
  type LibrarySortOrder,
} from '../api/client'
import { errorDetail } from '../api/error'
import { i18n } from '../i18n'
import { usePerfStore } from './perf'
import { useToastStore } from './toasts'
import { validateUploadFile } from '../api/uploadValidation'
import type { LayerAlgorithm } from './job'

// Hoisted out of the ``filteredSorted`` computed (audit B3): constructing
// an Intl.Collator is non-trivial, and rebuilding one on every re-sort
// (each search keystroke / sort toggle) was pure waste. One shared,
// locale-agnostic, numeric-aware collator serves every comparison.
const NAME_COLLATOR = new Intl.Collator(undefined, { sensitivity: 'base', numeric: true })

// File-level snapshot of the print settings for a library entry.
// Persisted across sessions so every new placement of the same file
// starts from the operator's last-applied settings instead of the
// default conversion. The v0.2 simplification dropped the multi-style
// "variants" wrapper; one style per file is kept in
// ``layer_algorithms`` + ``visibility`` directly.
export interface SavedFileSettings {
  layer_algorithms: Record<string, LayerAlgorithm>
  visibility: Record<string, boolean>
  // The full editor configuration bag (``buildBitmapOptions`` output:
  // segmentation method, master style id, preprocess adjustments, per-
  // style knobs, curves…) the file was last applied with. Persisted
  // alongside the per-layer state so reopening the editor on a
  // configured file restores the *chosen config* — not just the layer
  // algorithms — instead of falling back to fresh defaults. Optional so
  // older snapshots (and files whose only state is layer overrides)
  // still load.
  last_options?: Record<string, unknown>
  // The on-plan footprint (mm) the file was last left at — set by a resize
  // or the editor's sheet picker (e.g. "fit to A5"). Restored on the next
  // placement so re-dropping a file the operator sized to A5 brings it
  // back at A5 instead of recomputing an auto-fit-to-workspace size.
  // Optional for back-compat with snapshots saved before footprint memory.
  footprint_mm?: { width_mm: number; height_mm: number }
}

const FILE_SETTINGS_KEY = 'omniplot.fileSettings.v2'
// v1 stored per-variant snapshots under ``omniplot.fileVariants.v1``;
// the v0.2 flattening collapses the active variant into
// ``layer_algorithms`` + ``visibility``. We migrate transparently on
// first load and then drop the legacy key.
const LEGACY_FILE_VARIANTS_KEY = 'omniplot.fileVariants.v1'

interface LegacyVariantSnapshot {
  id: string
  layer_algorithms?: Record<string, LayerAlgorithm>
  visibility?: Record<string, boolean>
}
interface LegacySavedFileVariants {
  variants?: LegacyVariantSnapshot[]
  active_variant_id?: string
  last_options?: Record<string, unknown>
}

// The library is the canonical store of uploaded sources. One entry per
// unique SHA-256 (deduplication happens on the backend); placements on the
// plan reference an entry by ``file_id``. The store keeps the lightweight
// list (no SVG) plus a small cache of fully-loaded details, fetched on
// demand when a placement needs to render.

export const useLibraryStore = defineStore('library', () => {
  const files = ref<LibraryFileRecord[]>([])
  const folders = ref<string[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const search = ref('')
  const sortKey = ref<LibrarySortKey>('date')
  const sortOrder = ref<LibrarySortOrder>('desc')
  // ``null`` = show all folders; ``""`` = root only.
  const folderFilter = ref<string | null>(null)

  // Detail cache: ``file_id`` -> full record with SVG + layers + metadata.
  // Each entry carries a full normalized SVG, so an unbounded cache grows
  // with every file the operator opens — tens of MB over a long browsing
  // session. Cap it FIFO: a miss just re-fetches via ``ensureDetail``, and
  // placements keep their own SVG copy, so eviction is always safe.
  const DETAIL_CACHE_MAX = 40
  const detailCache = ref<Record<string, LibraryFileDetail>>({})

  // Insert/replace a detail, evicting the oldest entry when over the cap.
  // Object key order is insertion order, so the first key is the oldest.
  function cacheDetail(detail: LibraryFileDetail): void {
    const next = { ...detailCache.value, [detail.file_id]: detail }
    const keys = Object.keys(next)
    if (keys.length > DETAIL_CACHE_MAX) delete next[keys[0]!]
    detailCache.value = next
  }

  // Per-file saved settings — keyed by file_id, persisted in localStorage.
  // Hydrated lazily from storage on first access; subsequent mutations
  // through ``saveFileSettings`` keep storage in sync.
  const fileSettings = ref<Record<string, SavedFileSettings>>(loadFileSettings())

  // Library integrity issues surfaced by the backend boot scan
  // (``GET /files/integrity`` — see backend lot L4). Lets the UI show a
  // banner and disable Edit on files that have lost the state needed
  // for /rerender, instead of letting the operator hit a 404 mid-flow.
  const integrityIssues = ref<IntegrityIssue[]>([])
  const integrityCheckedAt = ref<string | null>(null)

  // Quick lookup so a Vue component can disable the Edit button on a
  // broken card without iterating ``integrityIssues`` each render.
  const brokenFileIds = computed(() => {
    const s = new Set<string>()
    for (const issue of integrityIssues.value) s.add(issue.file_id)
    return s
  })

  function loadFileSettings(): Record<string, SavedFileSettings> {
    try {
      const raw = localStorage.getItem(FILE_SETTINGS_KEY)
      if (raw) {
        const parsed = JSON.parse(raw) as Record<string, SavedFileSettings>
        return parsed && typeof parsed === 'object' ? parsed : {}
      }
      // v1 → v2 migration: collapse each entry's variants list down to
      // the active snapshot. We only run this once because the legacy
      // key is removed after a successful read.
      const legacyRaw = localStorage.getItem(LEGACY_FILE_VARIANTS_KEY)
      if (!legacyRaw) return {}
      const legacy = JSON.parse(legacyRaw) as Record<string, LegacySavedFileVariants>
      const migrated: Record<string, SavedFileSettings> = {}
      for (const [fileId, entry] of Object.entries(legacy ?? {})) {
        if (!entry || typeof entry !== 'object') continue
        const variants = Array.isArray(entry.variants) ? entry.variants : []
        const active = variants.find((v) => v.id === entry.active_variant_id) ?? variants[0] ?? null
        migrated[fileId] = {
          layer_algorithms: { ...(active?.layer_algorithms ?? {}) },
          visibility: { ...(active?.visibility ?? {}) },
          last_options: entry.last_options ? { ...entry.last_options } : undefined,
        }
      }
      try {
        localStorage.setItem(FILE_SETTINGS_KEY, JSON.stringify(migrated))
        localStorage.removeItem(LEGACY_FILE_VARIANTS_KEY)
      } catch {
        // best-effort: leave the legacy key in place so a future load can retry.
      }
      return migrated
    } catch {
      return {}
    }
  }

  function persistFileSettingsNow(): void {
    try {
      localStorage.setItem(FILE_SETTINGS_KEY, JSON.stringify(fileSettings.value))
    } catch {
      // localStorage unavailable / full — non-fatal, settings just won't
      // survive the next reload.
    }
  }

  // Debounced write-behind. ``saveFileSettings`` fires once per layer per
  // pointer event while the operator drags a master-style slider
  // (slider → applyMasterStyleToLayers → per-layer applyLayerAlgorithm →
  // autoSyncFileSettings); a synchronous JSON.stringify + setItem of the
  // whole settings blob on each of those visibly stutters the drag on
  // Pi-class hardware. 300 ms trailing collapses the burst into one
  // write; ``beforeunload`` flushes so a quick tab close can't lose the
  // last edit.
  let persistTimer: ReturnType<typeof setTimeout> | null = null
  function persistFileSettings(): void {
    if (persistTimer) clearTimeout(persistTimer)
    persistTimer = setTimeout(() => {
      persistTimer = null
      persistFileSettingsNow()
    }, 300)
  }

  /** Write any pending (debounced) settings immediately. */
  function flushFileSettings(): void {
    if (persistTimer) {
      clearTimeout(persistTimer)
      persistTimer = null
      persistFileSettingsNow()
    }
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', flushFileSettings)
  }

  function saveFileSettings(
    fileId: string,
    settings: {
      layer_algorithms: Record<string, LayerAlgorithm>
      visibility: Record<string, boolean>
      last_options?: Record<string, unknown>
      footprint_mm?: { width_mm: number; height_mm: number }
    },
  ): void {
    if (!fileId) return
    // Preserve a previously-saved ``last_options`` / ``footprint_mm`` when
    // this call doesn't carry one (e.g. a pure visibility toggle whose
    // options haven't been recomputed) so we never blank out a remembered
    // config or footprint.
    const prior = fileSettings.value[fileId]
    fileSettings.value = {
      ...fileSettings.value,
      [fileId]: {
        layer_algorithms: { ...settings.layer_algorithms },
        visibility: { ...settings.visibility },
        last_options: settings.last_options
          ? { ...settings.last_options }
          : prior?.last_options
            ? { ...prior.last_options }
            : undefined,
        footprint_mm: settings.footprint_mm
          ? { ...settings.footprint_mm }
          : prior?.footprint_mm
            ? { ...prior.footprint_mm }
            : undefined,
      },
    }
    persistFileSettings()
  }

  function getFileSettings(fileId: string): SavedFileSettings | null {
    const saved = fileSettings.value[fileId]
    if (!saved) return null
    return {
      layer_algorithms: { ...saved.layer_algorithms },
      visibility: { ...saved.visibility },
      last_options: saved.last_options ? { ...saved.last_options } : undefined,
      footprint_mm: saved.footprint_mm ? { ...saved.footprint_mm } : undefined,
    }
  }

  // A file is considered "configured" when its saved settings carry an
  // explicit per-layer algorithm or a remembered editor config — i.e.
  // the operator has actually tweaked the conversion. Drives the green
  // accent in FilesPane.
  function hasFileSettings(fileId: string): boolean {
    const saved = fileSettings.value[fileId]
    if (!saved) return false
    if (saved.last_options && Object.keys(saved.last_options).length > 0) return true
    return Object.keys(saved.layer_algorithms ?? {}).length > 0
  }

  function dropFileSettings(fileId: string): void {
    if (!(fileId in fileSettings.value)) return
    const next = { ...fileSettings.value }
    delete next[fileId]
    fileSettings.value = next
    persistFileSettings()
  }

  const filteredSorted = computed<LibraryFileRecord[]>(() => {
    const q = search.value.trim().toLowerCase()
    const ff = folderFilter.value
    let rows = files.value.filter((f) => {
      if (ff !== null && f.folder !== ff) return false
      if (q && !f.source_file.toLowerCase().includes(q)) return false
      return true
    })
    const direction = sortOrder.value === 'asc' ? 1 : -1
    rows = [...rows].sort((a, b) => {
      let cmp = 0
      if (sortKey.value === 'name') {
        cmp = NAME_COLLATOR.compare(a.source_file, b.source_file)
      } else if (sortKey.value === 'type') {
        cmp = NAME_COLLATOR.compare(a.source_mime, b.source_mime)
      } else {
        cmp = a.created_at.localeCompare(b.created_at)
      }
      return cmp * direction
    })
    return rows
  })

  async function refresh(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [list, folderList] = await Promise.all([apiList(), apiListFolders()])
      files.value = list
      folders.value = folderList
    } catch (err) {
      error.value = errorDetail(err, i18n.global.t('library.loadFailed'))
      useToastStore().error(error.value)
    } finally {
      loading.value = false
    }
  }

  function _mergeRecord(record: LibraryFileRecord): void {
    const idx = files.value.findIndex((f) => f.file_id === record.file_id)
    if (idx >= 0) {
      files.value = [...files.value.slice(0, idx), record, ...files.value.slice(idx + 1)]
    } else {
      files.value = [record, ...files.value]
    }
    if (record.folder && !folders.value.includes(record.folder)) {
      folders.value = [...folders.value, record.folder].sort()
    }
  }

  async function upload(
    file: File,
    options: {
      folder?: string
      convertOptions?: Record<string, unknown>
      onProgress?: (percent: number) => void
      signal?: AbortSignal
      // Skip surfacing toasts from this store — the upper-layer caller
      // (job store) wants to drive its own progress toast and would
      // otherwise show duplicates. Warnings + dedup info still get
      // toasted because they have no equivalent on the caller side.
      silent?: boolean
    } = {},
  ): Promise<{ file: LibraryFileDetail; existing: boolean } | null> {
    // Client-side guard — refuse before opening a network round-trip
    // so the operator gets immediate feedback and an oversize / wrong-
    // type file never even hits the server.
    const validation = validateUploadFile(file)
    if (validation) {
      error.value = validation.message
      if (!options.silent) useToastStore().error(validation.message)
      return null
    }
    loading.value = true
    error.value = null
    // Time the round-trip upload + conversion: this is the
    // ``time_to_first_preview`` KPI (perf overlay, roadmap C.8). The
    // request emits one sample on completion regardless of success,
    // so the overlay reflects real operator-perceived latency.
    const perf = usePerfStore()
    const tStart = performance.now()
    try {
      // Dedup pre-check. When the operator isn't changing conversion options
      // (a plain library add — not an editor re-apply, which must re-convert),
      // hash the bytes locally and ask the backend whether this exact file
      // already exists. A hit lets us skip the entire upload + convert
      // round-trip, the dominant cost when re-adding a file already in the
      // library. Best-effort: a missing WebCrypto (insecure origin) or a
      // failed lookup just falls through to a normal upload below.
      if (!options.convertOptions && !options.signal?.aborted) {
        try {
          const hash = await sha256Hex(file)
          if (hash && !options.signal?.aborted) {
            const hit = await lookupLibraryFileByHash(hash)
            if (hit) {
              _mergeRecord(hit)
              cacheDetail(hit)
              if (!options.silent) {
                useToastStore().info(
                  i18n.global.t('library.dedupedToast', { name: hit.source_file }),
                )
              }
              return { file: hit, existing: true }
            }
          }
        } catch {
          // Non-fatal — fall through to a full upload.
        }
      }
      const result = await uploadToLibrary(file, options.folder ?? '', options.convertOptions, {
        onProgress: options.onProgress,
        signal: options.signal,
      })
      _mergeRecord(result.file)
      cacheDetail(result.file)
      const toasts = useToastStore()
      for (const w of (result.file.warnings ?? []).slice(0, 3)) toasts.warning(w)
      if ((result.file.warnings ?? []).length > 3) {
        toasts.warning(
          i18n.global.t('toast.moreWarnings', {
            count: (result.file.warnings ?? []).length - 3,
          }),
        )
      }
      if (result.existing && !options.silent) {
        toasts.info(i18n.global.t('library.dedupedToast', { name: result.file.source_file }))
      }
      return result
    } catch (err) {
      // ``CanceledError`` is what axios throws when an AbortController
      // fires; we surface a discreet info toast (not an error) and let
      // the caller decide whether to retry.
      const isCancelled =
        (err as { name?: string; code?: string }).name === 'CanceledError' ||
        (err as { code?: string }).code === 'ERR_CANCELED'
      if (isCancelled) {
        error.value = null
        if (!options.silent) {
          useToastStore().info(i18n.global.t('toast.uploadCancelled'))
        }
        return null
      }
      const message = errorDetail(err, i18n.global.t('upload.failed'))
      error.value = message
      if (!options.silent) useToastStore().error(message)
      return null
    } finally {
      loading.value = false
      perf.recordTiming('time_to_first_preview', performance.now() - tStart, file.name)
    }
  }

  // In-flight dedup so the FilesPane mount + thumbnail prefetch watch
  // doesn't spawn N parallel GETs for the same file id when called in
  // quick succession (the watch re-fires on every search / sort /
  // folder change, and the cached detail isn't visible until the
  // response lands). Keyed by file id; entries are removed in a
  // ``finally`` so a failed fetch is retried by the next caller
  // instead of permanently caching a rejection.
  const detailInflight = new Map<string, Promise<LibraryFileDetail | null>>()

  async function ensureDetail(fileId: string): Promise<LibraryFileDetail | null> {
    const cached = detailCache.value[fileId]
    if (cached) return cached
    const pending = detailInflight.get(fileId)
    if (pending) return pending
    const promise = (async () => {
      try {
        const detail = await apiGet(fileId)
        cacheDetail(detail)
        return detail
      } catch (err) {
        error.value = errorDetail(err, i18n.global.t('library.loadFailed'))
        return null
      } finally {
        detailInflight.delete(fileId)
      }
    })()
    detailInflight.set(fileId, promise)
    return promise
  }

  function getDetail(fileId: string): LibraryFileDetail | null {
    return detailCache.value[fileId] ?? null
  }

  function getRecord(fileId: string): LibraryFileRecord | null {
    return files.value.find((f) => f.file_id === fileId) ?? null
  }

  async function rename(fileId: string, newName: string): Promise<void> {
    try {
      const updated = await apiPatch(fileId, { source_file: newName })
      _mergeRecord(updated)
      const cached = detailCache.value[fileId]
      if (cached) {
        detailCache.value = {
          ...detailCache.value,
          [fileId]: { ...cached, source_file: updated.source_file },
        }
      }
    } catch (err) {
      useToastStore().error(errorDetail(err, i18n.global.t('library.renameFailed')))
    }
  }

  async function setFolder(fileId: string, folder: string): Promise<void> {
    try {
      const updated = await apiPatch(fileId, { folder })
      _mergeRecord(updated)
      const cached = detailCache.value[fileId]
      if (cached) {
        detailCache.value = {
          ...detailCache.value,
          [fileId]: { ...cached, folder: updated.folder },
        }
      }
      // Refresh distinct folder list (an old folder may now be empty).
      try {
        folders.value = await apiListFolders()
      } catch {
        // best-effort; keep stale list
      }
    } catch (err) {
      useToastStore().error(errorDetail(err, i18n.global.t('library.moveFailed')))
    }
  }

  async function remove(fileId: string): Promise<void> {
    try {
      await apiDelete(fileId)
      files.value = files.value.filter((f) => f.file_id !== fileId)
      const next = { ...detailCache.value }
      delete next[fileId]
      detailCache.value = next
      dropFileSettings(fileId)
      try {
        folders.value = await apiListFolders()
      } catch {
        // best-effort
      }
    } catch (err) {
      useToastStore().error(errorDetail(err, i18n.global.t('library.deleteFailed')))
    }
  }

  function clearCache(): void {
    detailCache.value = {}
  }

  async function refreshIntegrity(): Promise<void> {
    // Best-effort: a transient network blip shouldn't gate the UI, so
    // failures leave the previous report in place. The banner consumer
    // reads ``integrityIssues.value`` directly and shows nothing when
    // it's empty (the normal, healthy case).
    try {
      const report = await getFilesIntegrity()
      integrityIssues.value = report.issues
      integrityCheckedAt.value = new Date().toISOString()
    } catch {
      // Keep stale data — don't blank out a known-issue list on a
      // momentary fetch failure.
    }
  }

  function isFileBroken(fileId: string): boolean {
    return brokenFileIds.value.has(fileId)
  }

  return {
    // state
    files,
    folders,
    loading,
    error,
    search,
    sortKey,
    sortOrder,
    folderFilter,
    detailCache,
    fileSettings,
    integrityIssues,
    integrityCheckedAt,
    // getters
    filteredSorted,
    brokenFileIds,
    // actions
    refresh,
    refreshIntegrity,
    isFileBroken,
    upload,
    ensureDetail,
    getDetail,
    getRecord,
    rename,
    setFolder,
    remove,
    clearCache,
    saveFileSettings,
    getFileSettings,
    hasFileSettings,
    dropFileSettings,
    flushFileSettings,
  }
})
