<script setup lang="ts">
// Single file row for FilesPane (L10 #5 extract).
//
// Pure presentational: receives the row + the optional preview SVG
// and emits intent events for add-to-plan / edit / move / remove /
// dragstart. The orchestrator forwards them to the library / job
// stores.
//
// UX audit (Lot 1, 2026-07-19): the primary action is an explicit
// "Add to plan" text button — drag-and-drop stays as the power-user
// shortcut but is no longer the only path (undiscoverable on touch).
// Secondary actions (move to folder, delete) collapse into a ``⋯``
// menu; Edit keeps a visible button since it's the second most-used
// action. Buttons are always visible — the previous hover-only
// reveal (``opacity-60 group-hover:opacity-100``) hid them entirely
// on tablets.

import { onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { LibraryFileRecord } from '../api/client'
import { useInViewport } from '../composables/useInViewport'
import { shortMime } from '../lib/labels'

const { t } = useI18n()

const props = defineProps<{
  file: LibraryFileRecord
  placementCount: number
  configured: boolean
  /** Sanitised SVG markup for the thumbnail (empty string when the
   *  file has no thumbnail yet — falls back to the MIME badge). */
  previewSvg: string
}>()

const emit = defineEmits<{
  /** Primary action: place this file on the plan. */
  add: [fileId: string]
  edit: [fileId: string]
  move: [file: LibraryFileRecord]
  remove: [file: LibraryFileRecord]
  dragstart: [event: DragEvent, file: LibraryFileRecord]
  /** Fired once when the row scrolls into view, so the pane can lazily
   *  fetch + sanitize this file's thumbnail (audit B3) instead of doing
   *  it for every row up front. */
  visible: [fileId: string]
}>()

// Defer the expensive thumbnail work to when the row is actually on screen.
const rootEl = ref<HTMLElement | null>(null)
const onScreen = useInViewport(rootEl, { rootMargin: '300px' })
watch(
  onScreen,
  (v) => {
    if (v) emit('visible', props.file.file_id)
  },
  { immediate: true },
)

// ``⋯`` overflow menu. Closes on outside click; the listener is only
// attached while open so idle rows cost nothing.
const menuOpen = ref(false)

function onDocClick(event: MouseEvent): void {
  if (!rootEl.value?.contains(event.target as Node)) menuOpen.value = false
}

watch(menuOpen, (open) => {
  if (typeof document === 'undefined') return
  if (open) document.addEventListener('click', onDocClick, true)
  else document.removeEventListener('click', onDocClick, true)
})

onBeforeUnmount(() => {
  if (typeof document !== 'undefined') document.removeEventListener('click', onDocClick, true)
})

function menuAction(action: 'move' | 'remove'): void {
  menuOpen.value = false
  if (action === 'move') emit('move', props.file)
  else emit('remove', props.file)
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<template>
  <li
    ref="rootEl"
    class="relative flex items-center gap-2 rounded border bg-slate-800 px-2 py-1.5 text-xs cursor-grab active:cursor-grabbing"
    :class="
      configured
        ? 'border-emerald-600 bg-emerald-950/30 hover:border-emerald-400'
        : 'border-slate-700 hover:border-slate-500'
    "
    draggable="true"
    :title="t('files.dragHint')"
    data-test="file-row"
    @dragstart="(e) => emit('dragstart', e, file)"
    @dblclick="emit('edit', file.file_id)"
  >
    <div
      class="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded border bg-white"
      :class="configured ? 'border-emerald-500/50' : 'border-slate-600'"
      :title="file.source_mime"
    >
      <div v-if="previewSvg" class="files-thumb h-full w-full" v-html="previewSvg" />
      <span v-else class="font-mono text-[9px] uppercase tracking-wider text-slate-500">
        {{ shortMime(file.source_mime) }}
      </span>
    </div>
    <div class="min-w-0 flex-1">
      <p
        class="truncate text-sm"
        :class="configured ? 'text-emerald-100' : 'text-slate-100'"
        :title="file.source_file"
      >
        {{ file.source_file }}
      </p>
      <p class="truncate text-[10px] text-slate-500">
        {{ formatSize(file.size_bytes) }}
        <span class="text-slate-700"> · </span>
        {{ file.layer_count }} {{ t('upload.layers', file.layer_count) }}
        <span v-if="placementCount" class="text-slate-700"> · </span>
        <span v-if="placementCount" class="text-emerald-400">
          {{ t('files.placements', { count: placementCount }) }}
        </span>
        <span v-if="file.folder" class="text-slate-700"> · </span>
        <span v-if="file.folder" class="text-slate-400">📁 {{ file.folder }}</span>
      </p>
    </div>
    <div class="flex shrink-0 items-center gap-1">
      <button
        type="button"
        class="rounded bg-emerald-700 px-2 py-1 text-[11px] font-semibold text-white hover:bg-emerald-600"
        data-test="file-row-add"
        @click.stop="emit('add', file.file_id)"
      >
        {{ t('files.addToPlan') }}
      </button>
      <button
        type="button"
        class="rounded bg-slate-700 px-1.5 py-1 text-[11px] text-slate-100 hover:bg-slate-600"
        :title="t('files.editTitle')"
        data-test="file-row-edit"
        @click.stop="emit('edit', file.file_id)"
      >
        ✎
      </button>
      <button
        type="button"
        class="rounded bg-slate-700 px-1.5 py-1 text-[11px] text-slate-100 hover:bg-slate-600"
        :title="t('files.moreActions')"
        :aria-label="t('files.moreActions')"
        :aria-expanded="menuOpen"
        data-test="file-row-menu"
        @click.stop="menuOpen = !menuOpen"
      >
        ⋯
      </button>
    </div>

    <!-- Overflow menu: secondary, destructive-adjacent actions. -->
    <div
      v-if="menuOpen"
      class="absolute right-1 top-full z-20 mt-1 w-40 overflow-hidden rounded border border-slate-600 bg-slate-800 shadow-xl"
      role="menu"
      data-test="file-row-menu-popover"
    >
      <button
        type="button"
        role="menuitem"
        class="block w-full px-3 py-2 text-left text-xs text-slate-100 hover:bg-slate-700"
        data-test="file-row-move"
        @click.stop="menuAction('move')"
      >
        📁 {{ t('files.moveTo') }}
      </button>
      <button
        type="button"
        role="menuitem"
        class="block w-full px-3 py-2 text-left text-xs text-red-300 hover:bg-red-900/40"
        data-test="file-row-remove"
        @click.stop="menuAction('remove')"
      >
        ✕ {{ t('files.remove') }}
      </button>
    </div>
  </li>
</template>

<style scoped>
:deep(.files-thumb svg) {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
