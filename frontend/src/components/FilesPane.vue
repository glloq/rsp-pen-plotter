<script setup lang="ts">
import DOMPurify from 'dompurify'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { LibraryFileRecord, LibrarySortKey } from '../api/client'
import { useJobStore } from '../stores/job'
import { useLibraryStore } from '../stores/library'
import { useUiStore } from '../stores/ui'

const { t } = useI18n()
const store = useJobStore()
const library = useLibraryStore()
const ui = useUiStore()

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
    return { file, placementCount, configured: placementCount > 0 }
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
  fileInput.value?.click()
}

async function onFileInputChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  for (const file of files) {
    await library.upload(file)
  }
  // Reset so picking the same file twice in a row still fires ``change``.
  input.value = ''
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

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function shortMime(mime: string): string {
  // Render compact: "image/svg+xml" → "SVG", "application/pdf" → "PDF".
  const subtype = mime.split('/')[1] ?? mime
  return subtype.replace(/\+.*$/, '').replace(/^vnd\..+\./, '').toUpperCase()
}

function onDragStart(event: DragEvent, file: LibraryFileRecord): void {
  if (!event.dataTransfer) return
  event.dataTransfer.setData('application/x-omniplot-library', file.file_id)
  event.dataTransfer.setData('text/plain', file.source_file)
  event.dataTransfer.effectAllowed = 'copy'
}
</script>

<template>
  <aside class="flex min-h-0 flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-900/40">
    <header class="border-b border-slate-700 px-3 py-2">
      <div class="flex items-center justify-between">
        <h2 class="text-xs uppercase tracking-wider text-slate-500">
          {{ t('files.title') }}
          <span v-if="rows.length" class="ml-1 text-slate-600">({{ rows.length }})</span>
        </h2>
        <button
          type="button"
          class="rounded bg-emerald-600 px-2 py-1 text-xs font-medium text-white hover:bg-emerald-500"
          @click="addFile"
        >
          + {{ t('files.addFile') }}
        </button>
      </div>

      <div class="mt-2 space-y-1">
        <input
          v-model="searchInput"
          type="search"
          :placeholder="t('files.search')"
          class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
          @input="onSearchInput"
        />
        <div class="flex items-center gap-1 text-[11px]">
          <select
            :value="library.sortKey"
            class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-1 py-1 text-slate-100"
            :title="t('files.sort')"
            @change="onSortChange"
          >
            <option value="name">{{ t('files.sortName') }}</option>
            <option value="date">{{ t('files.sortDate') }}</option>
            <option value="type">{{ t('files.sortType') }}</option>
          </select>
          <button
            type="button"
            class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100 hover:border-slate-500"
            :title="library.sortOrder === 'asc' ? t('files.sortAsc') : t('files.sortDesc')"
            @click="onOrderToggle"
          >
            {{ library.sortOrder === 'asc' ? '▲' : '▼' }}
          </button>
          <select
            :value="library.folderFilter === null ? '__all__' : library.folderFilter"
            class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-1 py-1 text-slate-100"
            :title="t('files.folder')"
            @change="onFolderChange"
          >
            <option value="__all__">{{ t('files.allFolders') }}</option>
            <option value="">{{ t('files.rootFolder') }}</option>
            <option v-for="f in library.folders" :key="f" :value="f">{{ f }}</option>
            <option value="__new__">{{ t('files.newFolder') }}</option>
          </select>
        </div>
      </div>
    </header>

    <div class="flex-1 overflow-y-auto p-2">
      <div
        v-if="!rows.length"
        class="flex h-full flex-col items-center justify-center gap-2 text-center text-slate-500"
      >
        <div class="text-4xl text-slate-700" aria-hidden="true">📄</div>
        <p class="text-sm text-slate-300">{{ t('files.empty') }}</p>
        <p class="max-w-[220px] text-xs text-slate-600">{{ t('files.emptyHint') }}</p>
      </div>

      <ul v-else class="space-y-1">
        <li
          v-for="row in rows"
          :key="row.file.file_id"
          class="group flex items-center gap-2 rounded border bg-slate-800 px-2 py-1.5 text-xs cursor-grab active:cursor-grabbing"
          :class="row.configured
            ? 'border-emerald-600 bg-emerald-950/30 hover:border-emerald-400'
            : 'border-slate-700 hover:border-slate-500'"
          draggable="true"
          :title="t('files.dragHint')"
          @dragstart="(e) => onDragStart(e, row.file)"
          @dblclick="editFile(row.file.file_id)"
        >
          <div
            class="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded border bg-white"
            :class="row.configured ? 'border-emerald-500/50' : 'border-slate-600'"
            :title="row.file.source_mime"
          >
            <div
              v-if="previewSvg(row.file.file_id)"
              v-html="previewSvg(row.file.file_id)"
              class="files-thumb h-full w-full"
            />
            <span
              v-else
              class="font-mono text-[9px] uppercase tracking-wider text-slate-500"
            >
              {{ shortMime(row.file.source_mime) }}
            </span>
          </div>
          <div class="min-w-0 flex-1">
            <p
              class="truncate text-sm"
              :class="row.configured ? 'text-emerald-100' : 'text-slate-100'"
              :title="row.file.source_file"
            >
              {{ row.file.source_file }}
            </p>
            <p class="truncate text-[10px] text-slate-500">
              {{ formatSize(row.file.size_bytes) }}
              <span class="text-slate-700"> · </span>
              {{ row.file.layer_count }} {{ t('upload.layers', row.file.layer_count) }}
              <span v-if="row.placementCount" class="text-slate-700"> · </span>
              <span v-if="row.placementCount" class="text-emerald-400">
                {{ t('files.placements', { count: row.placementCount }) }}
              </span>
              <span v-if="row.file.folder" class="text-slate-700"> · </span>
              <span v-if="row.file.folder" class="text-slate-400">📁 {{ row.file.folder }}</span>
            </p>
          </div>
          <div class="flex shrink-0 items-center gap-0.5 opacity-60 group-hover:opacity-100">
            <button
              type="button"
              class="rounded bg-slate-700 px-1.5 py-1 text-[11px] text-slate-100 hover:bg-slate-600"
              :title="t('files.editTitle')"
              @click.stop="editFile(row.file.file_id)"
            >
              ✎
            </button>
            <button
              type="button"
              class="rounded bg-slate-700 px-1.5 py-1 text-[11px] text-slate-100 hover:bg-slate-600"
              :title="t('files.moveTo')"
              @click.stop="moveFile(row.file)"
            >
              📁
            </button>
            <button
              type="button"
              class="rounded text-slate-500 hover:text-red-300 px-1"
              :title="t('files.remove')"
              @click.stop="removeFile(row.file)"
            >
              ✕
            </button>
          </div>
        </li>
      </ul>
    </div>

    <input
      ref="fileInput"
      type="file"
      multiple
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
