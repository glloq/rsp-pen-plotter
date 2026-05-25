<script setup lang="ts">
import DOMPurify from 'dompurify'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { LibraryFileRecord, LibrarySortKey } from '../api/client'
import { FILE_ACCEPT } from '../composables/useFileManager'
import { validateUploadFile } from '../api/uploadValidation'
import { useJobStore } from '../stores/job'
import { useLibraryStore } from '../stores/library'
import { useToastStore } from '../stores/toasts'
import { useUiStore } from '../stores/ui'
import FileLibraryFilters from './FileLibraryFilters.vue'
import FileListRow from './FileListRow.vue'

const { t } = useI18n()
const store = useJobStore()
const library = useLibraryStore()
const toasts = useToastStore()
const ui = useUiStore()

// Per-pane upload state. The library store has its own ``loading`` flag
// but it's also used by the initial ``/files`` listing fetch, so we keep
// a dedicated counter for the upload flow — drives the button label,
// disables re-entry while a batch is in progress.
const uploadingCount = ref(0)
const uploadingTotal = ref(0)
const uploadProgress = ref<{ name: string; percent: number } | null>(null)
// AbortController for the in-flight upload (one at a time — uploads are
// sequential so we only ever need a single handle). ``Cancel`` on the
// button aborts the current file; the loop catches the rejection and
// stops on its own.
let activeController: AbortController | null = null

const isUploading = computed(() => uploadingCount.value > 0)

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
  for (const p of store.placements) {
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
// file and only recompute when the cached detail isn't there yet.
const thumbCache = new Map<string, string>()
function previewSvg(fileId: string): string | null {
  const cached = thumbCache.get(fileId)
  if (cached !== undefined) return cached || null
  const detail = library.getDetail(fileId)
  if (!detail?.svg) return null
  const clean = DOMPurify.sanitize(detail.svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
  })
  thumbCache.set(fileId, clean)
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
    // a cancel request for the current file rather than queueing a new
    // file picker dialog.
    activeController?.abort()
    return
  }
  fileInput.value?.click()
}

// Sequentially upload a list of files through the library store with
// client-side validation, per-file progress, and cancel support. Errors
// on one file don't abort the batch — the failed file gets a toast and
// the next one starts.
async function uploadFiles(files: File[]): Promise<void> {
  if (files.length === 0) return
  // Up-front validation — surface every issue at once so the operator
  // sees the rejected files before any network work starts.
  const accepted: File[] = []
  for (const file of files) {
    const issue = validateUploadFile(file)
    if (issue) {
      toasts.error(`${file.name}: ${issue.message}`)
    } else {
      accepted.push(file)
    }
  }
  if (accepted.length === 0) return
  uploadingTotal.value = accepted.length
  uploadingCount.value = accepted.length
  try {
    for (const file of accepted) {
      const controller = new AbortController()
      activeController = controller
      uploadProgress.value = { name: file.name, percent: 0 }
      try {
        await library.upload(file, {
          signal: controller.signal,
          onProgress: (percent: number) => {
            if (controller.signal.aborted) return
            uploadProgress.value = { name: file.name, percent }
          },
        })
      } finally {
        if (activeController === controller) activeController = null
        uploadingCount.value -= 1
      }
    }
  } finally {
    uploadingCount.value = 0
    uploadingTotal.value = 0
    uploadProgress.value = null
    activeController = null
  }
}

async function onFileInputChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  // Reset the value first — if the upload throws we still want
  // ``change`` to fire next time the same file is picked.
  input.value = ''
  await uploadFiles(files)
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

async function onPaneDrop(event: DragEvent): Promise<void> {
  paneDragOver.value = false
  if (!event.dataTransfer?.files?.length) return
  event.preventDefault()
  if (isUploading.value) {
    toasts.info(t('files.uploadInProgress'))
    return
  }
  await uploadFiles(Array.from(event.dataTransfer.files))
}

async function editFile(fileId: string): Promise<void> {
  // Reuse the most recent placement of this file if there is one;
  // otherwise create a new placement and open it for editing.
  const existing = store.placements.find((p) => p.library_file_id === fileId)
  if (existing) {
    store.selectPlacement(existing.id)
  } else {
    const newId = await store.createPlacementFromLibrary(fileId)
    if (!newId) return
    store.selectPlacement(newId)
  }
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
  if (!window.confirm(t('files.deleteConfirm', { name: file.source_file }))) return
  await library.remove(file.file_id)
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
            <template v-else-if="uploadProgress && uploadProgress.percent < 100">
              {{ uploadProgress.percent }}%
            </template>
            <template v-else>{{ t('upload.converting') }}</template>
          </span>
        </button>
      </div>
      <p
        v-if="isUploading && uploadProgress"
        class="mt-1 truncate text-[10px] text-slate-400"
        :title="uploadProgress.name"
      >
        {{
          uploadingTotal > 1
            ? `(${uploadingTotal - uploadingCount + 1}/${uploadingTotal}) ${uploadProgress.name}`
            : uploadProgress.name
        }}
      </p>

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
