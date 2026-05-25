import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  deleteLibraryFile as apiDelete,
  getLibraryFile as apiGet,
  listLibraryFiles as apiList,
  listLibraryFolders as apiListFolders,
  patchLibraryFile as apiPatch,
  uploadToLibrary,
  type LibraryFileDetail,
  type LibraryFileRecord,
  type LibrarySortKey,
  type LibrarySortOrder,
} from '../api/client'
import { errorDetail } from '../api/error'
import { i18n } from '../i18n'
import { useToastStore } from './toasts'
import { validateUploadFile } from '../api/uploadValidation'

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
  const detailCache = ref<Record<string, LibraryFileDetail>>({})

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
      files.value = [
        ...files.value.slice(0, idx),
        record,
        ...files.value.slice(idx + 1),
      ]
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
    try {
      const result = await uploadToLibrary(
        file,
        options.folder ?? '',
        options.convertOptions,
        { onProgress: options.onProgress, signal: options.signal },
      )
      _mergeRecord(result.file)
      detailCache.value = { ...detailCache.value, [result.file.file_id]: result.file }
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
      const isCancelled = (err as { name?: string; code?: string }).name === 'CanceledError'
        || (err as { code?: string }).code === 'ERR_CANCELED'
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
    }
  }

  async function ensureDetail(fileId: string): Promise<LibraryFileDetail | null> {
    const cached = detailCache.value[fileId]
    if (cached) return cached
    try {
      const detail = await apiGet(fileId)
      detailCache.value = { ...detailCache.value, [fileId]: detail }
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
    // getters
    filteredSorted,
    // actions
    refresh,
    upload,
    ensureDetail,
    getDetail,
    getRecord,
    rename,
    setFolder,
    remove,
    clearCache,
  }
})
