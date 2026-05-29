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
import type { Variant } from './job'

// File-level snapshot of the print settings (variants) for a library
// entry. Persisted across sessions so every new placement of the same
// file starts from the operator's last-applied settings, instead of the
// default conversion.
export interface SavedFileVariants {
  variants: Variant[]
  active_variant_id: string
  // The full editor configuration bag (``buildBitmapOptions`` output:
  // segmentation method, master style id, preprocess adjustments, per-
  // style knobs, curves…) the file was last applied with. Persisted
  // alongside the per-layer variants so reopening the editor on a
  // configured file restores the *chosen config* — not just the layer
  // algorithms — instead of falling back to fresh defaults. Optional so
  // older snapshots (and files whose only state is layer overrides)
  // still load.
  last_options?: Record<string, unknown>
}

const FILE_VARIANTS_KEY = 'omniplot.fileVariants.v1'

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

  // Per-file saved variants — keyed by file_id, persisted in localStorage.
  // Hydrated lazily from storage on first access; subsequent mutations
  // through ``saveFileVariants`` keep storage in sync.
  const fileVariants = ref<Record<string, SavedFileVariants>>(loadFileVariants())

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

  function loadFileVariants(): Record<string, SavedFileVariants> {
    try {
      const raw = localStorage.getItem(FILE_VARIANTS_KEY)
      if (!raw) return {}
      const parsed = JSON.parse(raw) as Record<string, SavedFileVariants>
      return parsed && typeof parsed === 'object' ? parsed : {}
    } catch {
      return {}
    }
  }

  function persistFileVariants(): void {
    try {
      localStorage.setItem(FILE_VARIANTS_KEY, JSON.stringify(fileVariants.value))
    } catch {
      // localStorage unavailable / full — non-fatal, settings just won't
      // survive the next reload.
    }
  }

  function cloneVariants(variants: Variant[]): Variant[] {
    return variants.map((v) => ({
      ...v,
      layer_algorithms: { ...v.layer_algorithms },
      visibility: { ...v.visibility },
    }))
  }

  function saveFileVariants(
    fileId: string,
    variants: Variant[],
    activeId: string,
    lastOptions?: Record<string, unknown>,
  ): void {
    if (!fileId) return
    // Preserve a previously-saved ``last_options`` when this call doesn't
    // carry one (e.g. a pure visibility toggle on a placement whose
    // options haven't been recomputed) so we never blank out a remembered
    // config.
    const prior = fileVariants.value[fileId]
    fileVariants.value = {
      ...fileVariants.value,
      [fileId]: {
        variants: cloneVariants(variants),
        active_variant_id: activeId,
        last_options: lastOptions
          ? { ...lastOptions }
          : prior?.last_options
            ? { ...prior.last_options }
            : undefined,
      },
    }
    persistFileVariants()
  }

  function getFileVariants(fileId: string): SavedFileVariants | null {
    const saved = fileVariants.value[fileId]
    if (!saved) return null
    return {
      variants: cloneVariants(saved.variants),
      active_variant_id: saved.active_variant_id,
      last_options: saved.last_options ? { ...saved.last_options } : undefined,
    }
  }

  // A file is considered "configured" when at least one of its saved
  // variants has an explicit per-layer algorithm — i.e. the operator has
  // actually tweaked the conversion. Drives the green accent in FilesPane.
  function hasFileSettings(fileId: string): boolean {
    const saved = fileVariants.value[fileId]
    if (!saved) return false
    // A non-empty per-layer override OR a remembered editor config
    // (master style / segmentation / preprocess) both count as "the
    // operator configured this file" — so the green accent matches what
    // "Edit from library" will actually restore.
    if (saved.last_options && Object.keys(saved.last_options).length > 0) return true
    return saved.variants.some((v) => Object.keys(v.layer_algorithms ?? {}).length > 0)
  }

  function dropFileVariants(fileId: string): void {
    if (!(fileId in fileVariants.value)) return
    const next = { ...fileVariants.value }
    delete next[fileId]
    fileVariants.value = next
    persistFileVariants()
  }

  const filteredSorted = computed<LibraryFileRecord[]>(() => {
    const q = search.value.trim().toLowerCase()
    const ff = folderFilter.value
    let rows = files.value.filter((f) => {
      if (ff !== null && f.folder !== ff) return false
      if (q && !f.source_file.toLowerCase().includes(q)) return false
      return true
    })
    const collator = new Intl.Collator(undefined, { sensitivity: 'base', numeric: true })
    const direction = sortOrder.value === 'asc' ? 1 : -1
    rows = [...rows].sort((a, b) => {
      let cmp = 0
      if (sortKey.value === 'name') {
        cmp = collator.compare(a.source_file, b.source_file)
      } else if (sortKey.value === 'type') {
        cmp = collator.compare(a.source_mime, b.source_mime)
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
      if (result.existing) {
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

  async function ensureDetail(fileId: string): Promise<LibraryFileDetail | null> {
    const cached = detailCache.value[fileId]
    if (cached) return cached
    try {
      const detail = await apiGet(fileId)
      cacheDetail(detail)
      return detail
    } catch (err) {
      error.value = errorDetail(err, i18n.global.t('library.loadFailed'))
      return null
    }
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
      dropFileVariants(fileId)
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
    fileVariants,
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
    saveFileVariants,
    getFileVariants,
    hasFileSettings,
    dropFileVariants,
  }
})
