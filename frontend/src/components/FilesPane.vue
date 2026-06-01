<script setup lang="ts">
import DOMPurify from 'dompurify'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { LibraryFileRecord, LibrarySortKey } from '../api/client'
import { confirmAction } from '../composables/confirm'
import { FILE_ACCEPT } from '../composables/useFileManager'
import { useJobStore } from '../stores/job'
import { useLibraryStore } from '../stores/library'
import { useUiStore } from '../stores/ui'
import { useUploadsStore } from '../stores/uploads'
import FileLibraryFilters from './FileLibraryFilters.vue'
import FileListRow from './FileListRow.vue'

const { t } = useI18n()
const store = useJobStore()
const library = useLibraryStore()
const ui = useUiStore()
// All upload orchestration (validation, the concurrency pool, per-file
// progress and the progress modal) lives in the uploads store so the
// pane button, pane drop and window-level drop share one path.
const uploads = useUploadsStore()

const isUploading = computed(() => uploads.active)

onMounted(() => {
  void library.refresh()
})

// Lightweight projection used by the template — keeps the row markup
// terse and lets us count plan placements per library entry once.
interface Row {
  file: LibraryFileRecord
  placementCount: number
  // A file is considered "configured / ready to print" when at least one
  // placement on the plan references it. Drives the green accent in the
  // list.
  configured: boolean
}

const rows = computed<Row[]>(() => {
  const counts = new Map<string, number>()
  // Use visiblePlacements — library-draft placements aren't on the sheet
  // and shouldn't count towards the "X placements" indicator (audit
  // 2026-05-27 — Edit must not mark the file as placed).
  for (const p of store.visiblePlacements) {
    if (p.library_file_id) {
      counts.set(p.library_file_id, (counts.get(p.library_file_id) ?? 0) + 1)
    }
  }
  return library.filteredSorted.map((file) => {
    const placementCount = counts.get(file.file_id) ?? 0
    // A file is considered "configured" once the operator has saved
    // per-layer settings for it (any variant with explicit algorithms).
    // The library snapshot survives placement removals, so a file stays
    // green even after it's been cleared from the plan.
    return {
      file,
      placementCount,
      configured: library.hasFileSettings(file.file_id),
    }
  })
})

// Fetch full SVG for each listed file so the row can show a mini preview.
// Detail is cached in the library store, so this is a no-op after the
// first hit per file.
watch(
  () => rows.value.map((r) => r.file.file_id),
  (ids) => {
    for (const id of ids) {
      if (!library.getDetail(id)) void library.ensureDetail(id)
    }
  },
  { immediate: true },
)

// Thumbnail cache keyed by file_id. Sanitizing through DOMPurify is the
// most expensive part of rendering the inline preview, so we memoize per
// file and only recompute when the cached detail isn't there yet. Bounded
// LRU (Map keeps insertion order): a miss just re-sanitizes, so capping
// keeps the sanitized-SVG strings from accumulating for the whole library.
const THUMB_CACHE_MAX = 60
const thumbCache = new Map<string, string>()
function previewSvg(fileId: string): string | null {
  const cached = thumbCache.get(fileId)
  if (cached !== undefined) {
    // Refresh recency so the active set survives eviction.
    thumbCache.delete(fileId)
    thumbCache.set(fileId, cached)
    return cached || null
  }
  const detail = library.getDetail(fileId)
  if (!detail?.svg) return null
  const clean = DOMPurify.sanitize(detail.svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
  })
  thumbCache.set(fileId, clean)
  if (thumbCache.size > THUMB_CACHE_MAX) {
    const oldest = thumbCache.keys().next().value
    if (oldest !== undefined) thumbCache.delete(oldest)
  }
  return clean
}

const searchInput = ref(library.search)
let searchTimer: ReturnType<typeof setTimeout> | null = null
function onSearchInput(): void {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    library.search = searchInput.value
  }, 180)
}

function onSortChange(event: Event): void {
  library.sortKey = (event.target as HTMLSelectElement).value as LibrarySortKey
}

function onOrderToggle(): void {
  library.sortOrder = library.sortOrder === 'asc' ? 'desc' : 'asc'
}

function onFolderChange(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  if (value === '__all__') {
    library.folderFilter = null
  } else if (value === '__new__') {
    const name = window.prompt(t('files.newFolderPrompt'))?.trim()
    if (name) {
      if (!library.folders.includes(name)) {
        library.folders = [...library.folders, name].sort()
      }
      library.folderFilter = name
    }
    // Reset the <select> back to the current filter regardless of result.
    ;(event.target as HTMLSelectElement).value =
      library.folderFilter === null ? '__all__' : library.folderFilter
  } else {
    library.folderFilter = value
  }
}

// Hidden <input type="file"> handle — clicked programmatically by the
// "Add a file" button so dropping the file into the library doesn't
// require the editor to be open.
const fileInput = ref<HTMLInputElement | null>(null)

function addFile(): void {
  if (isUploading.value) {
    // Operator clicked while a batch is in progress — interpret that as
    // a cancel request rather than queueing a new file picker dialog.
    uploads.cancelAll()
    return
  }
  fileInput.value?.click()
}

function onFileInputChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  // Reset the value first — if the picker is reopened with the same file
  // we still want ``change`` to fire next time.
  input.value = ''
  uploads.start(files)
}

// Pane-level drag-and-drop. Lets the operator drop files straight into
// the library list without going through the file picker. Defensively
// guarded by ``isUploading`` so an in-flight batch can finish before a
// new one starts (no concurrent uploads racing on disk dedup).
const paneDragOver = ref(false)

function onPaneDragOver(event: DragEvent): void {
  // Only respond to drags that carry actual files. ``dataTransfer.types``
  // includes ``"Files"`` only for OS-level drags, never for in-app drags
  // (which use our ``application/x-omniplot-*`` mime).
  if (!event.dataTransfer?.types?.includes('Files')) return
  event.preventDefault()
  paneDragOver.value = true
}

function onPaneDragLeave(event: DragEvent): void {
  // Ignore the bubbling dragleave fired when the pointer enters a
  // child element — only clear the highlight when the pointer leaves
  // the pane entirely.
  if (
    event.currentTarget instanceof Node &&
    event.relatedTarget instanceof Node &&
    event.currentTarget.contains(event.relatedTarget)
  ) {
    return
  }
  paneDragOver.value = false
}

function onPaneDrop(event: DragEvent): void {
  paneDragOver.value = false
  if (!event.dataTransfer?.files?.length) return
  event.preventDefault()
  // The uploads store appends to the running batch, so a drop during an
  // in-flight import just queues more files — no re-entry guard needed.
  uploads.start(event.dataTransfer.files)
}

async function editFile(fileId: string): Promise<void> {
  // "Edit" is conversion-settings only — it must NOT put the file on
  // the sheet just because the operator wanted to tweak knobs (audit
  // 2026-05-27). Resolution order:
  //   1. A visible (sheet-placed) placement for this file exists →
  //      reuse it. Modal edits apply to the live placement.
  //   2. A library-draft placement for this file already exists →
  //      reopen it. The draft is invisible on the sheet but holds
  //      the operator's last conversion settings.
  //   3. Otherwise create a fresh library-draft placement. It stays
  //      invisible until the operator explicitly clicks "Add to plan"
  //      in the modal footer (materializeLibraryDraft).
  const visible = store.placements.find((p) => p.library_file_id === fileId && !p.is_library_draft)
  if (visible) {
    store.selectPlacement(visible.id)
    ui.openEditModal()
    return
  }
  const draft = store.placements.find((p) => p.library_file_id === fileId && p.is_library_draft)
  if (draft) {
    store.selectPlacement(draft.id)
    ui.openEditModal()
    return
  }
  const newId = await store.createPlacementFromLibrary(fileId, undefined, {
    asDraft: true,
  })
  if (!newId) return
  store.selectPlacement(newId)
  ui.openEditModal()
}

async function moveFile(file: LibraryFileRecord): Promise<void> {
  const existing = library.folders.join(', ')
  const next = window
    .prompt(`${t('files.moveTo')}${existing ? ` (${existing})` : ''}`, file.folder)
    ?.trim()
  if (next !== undefined && next !== file.folder) {
    await library.setFolder(file.file_id, next)
  }
}

async function removeFile(file: LibraryFileRecord): Promise<void> {
  const confirmed = await confirmAction({
    title: t('files.deleteTitle'),
    message: t('files.deleteConfirm', { name: file.source_file }),
    confirmLabel: t('files.remove'),
    cancelLabel: t('confirm.cancel'),
    danger: true,
  })
  if (!confirmed) return
  await library.remove(file.file_id)
  // Drop any placement (visible or "Edit from library" draft) backed by the
  // deleted file so it can't linger on the plan and leak into a later
  // generated G-code.
  store.removePlacementsForFile(file.file_id)
}

function onDragStart(event: DragEvent, file: LibraryFileRecord): void {
  if (!event.dataTransfer) return
  event.dataTransfer.setData('application/x-omniplot-library', file.file_id)
  event.dataTransfer.setData('text/plain', file.source_file)
  event.dataTransfer.effectAllowed = 'copy'
}
</script>

<template>
  <aside
    class="relative flex min-h-0 flex-col overflow-hidden rounded-lg border bg-slate-900/40 transition-colors"
    :class="paneDragOver ? 'border-emerald-500 bg-emerald-950/30' : 'border-slate-700'"
    @dragenter.prevent="onPaneDragOver"
    @dragover.prevent="onPaneDragOver"
    @dragleave="onPaneDragLeave"
    @drop="onPaneDrop"
  >
    <header class="border-b border-slate-700 px-3 py-2">
      <div class="flex items-center justify-between gap-2">
        <h2 class="text-xs uppercase tracking-wider text-slate-500">
          {{ t('files.title') }}
          <span v-if="rows.length" class="ml-1 text-slate-600">({{ rows.length }})</span>
        </h2>
        <button
          type="button"
          class="flex shrink-0 items-center gap-1.5 rounded px-2 py-1 text-xs font-medium text-white transition-colors disabled:cursor-not-allowed"
          :class="
            isUploading ? 'bg-slate-600 hover:bg-slate-500' : 'bg-emerald-600 hover:bg-emerald-500'
          "
          :title="isUploading ? t('upload.cancel') : t('files.addFile')"
          @click="addFile"
        >
          <span
            v-if="isUploading"
            class="inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-white"
            aria-hidden="true"
          />
          <span class="truncate">
            <template v-if="!isUploading">+ {{ t('files.addFile') }}</template>
            <template v-else>{{ t('upload.cancel') }}</template>
          </span>
        </button>
      </div>

      <FileLibraryFilters
        :search-input="searchInput"
        :sort-key="library.sortKey"
        :sort-order="library.sortOrder"
        :folder-filter="library.folderFilter"
        :folders="library.folders"
        @update:search-input="(v) => (searchInput = v)"
        @search-input="onSearchInput"
        @sort-change="onSortChange"
        @order-toggle="onOrderToggle"
        @folder-change="onFolderChange"
      />
    </header>

    <div class="flex-1 overflow-y-auto p-2">
      <div
        v-if="paneDragOver"
        class="pointer-events-none absolute inset-0 flex items-center justify-center bg-emerald-950/60 text-emerald-100"
      >
        <p class="text-sm font-medium">📥 {{ t('files.dropToImport') }}</p>
      </div>
      <div
        v-if="!rows.length"
        class="flex h-full flex-col items-center justify-center gap-2 text-center text-slate-500"
      >
        <div class="text-4xl text-slate-700" aria-hidden="true">📄</div>
        <p class="text-sm text-slate-300">{{ t('files.empty') }}</p>
        <p class="max-w-[220px] text-xs text-slate-600">{{ t('files.emptyHint') }}</p>
      </div>

      <ul v-else class="space-y-1">
        <FileListRow
          v-for="row in rows"
          :key="row.file.file_id"
          v-memo="[
            row.file.file_id,
            row.file.source_file,
            row.placementCount,
            row.configured,
            previewSvg(row.file.file_id) ?? '',
          ]"
          :file="row.file"
          :placement-count="row.placementCount"
          :configured="row.configured"
          :preview-svg="previewSvg(row.file.file_id) ?? ''"
          @edit="editFile"
          @move="moveFile"
          @remove="removeFile"
          @dragstart="onDragStart"
        />
      </ul>
    </div>

    <input
      ref="fileInput"
      type="file"
      multiple
      :accept="FILE_ACCEPT"
      class="hidden"
      @change="onFileInputChange"
    />
  </aside>
</template>

<style scoped>
/* Force inline SVG previews to behave as scalable thumbnails: ignore any
   inline width/height baked into the source, scale to fit the parent
   square via the existing viewBox. */
.files-thumb :deep(svg) {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
