<script setup lang="ts">
// Single file row for FilesPane (L10 #5 extract).
//
// Pure presentational: receives the row + the optional preview SVG
// and emits intent events for edit / move / remove / dragstart. The
// orchestrator forwards them to the library / job stores.

import { useI18n } from 'vue-i18n'
import type { LibraryFileRecord } from '../api/client'
import { shortMime } from '../lib/labels'

const { t } = useI18n()

defineProps<{
  file: LibraryFileRecord
  placementCount: number
  configured: boolean
  /** Sanitised SVG markup for the thumbnail (empty string when the
   *  file has no thumbnail yet — falls back to the MIME badge). */
  previewSvg: string
}>()

const emit = defineEmits<{
  edit: [fileId: string]
  move: [file: LibraryFileRecord]
  remove: [file: LibraryFileRecord]
  dragstart: [event: DragEvent, file: LibraryFileRecord]
}>()

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<template>
  <li
    class="group flex items-center gap-2 rounded border bg-slate-800 px-2 py-1.5 text-xs cursor-grab active:cursor-grabbing"
    :class="
      configured
        ? 'border-emerald-600 bg-emerald-950/30 hover:border-emerald-400'
        : 'border-slate-700 hover:border-slate-500'
    "
    draggable="true"
    :title="t('files.dragHint')"
    @dragstart="(e) => emit('dragstart', e, file)"
    @dblclick="emit('edit', file.file_id)"
  >
    <div
      class="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded border bg-white"
      :class="configured ? 'border-emerald-500/50' : 'border-slate-600'"
      :title="file.source_mime"
    >
      <div v-if="previewSvg" v-html="previewSvg" class="files-thumb h-full w-full" />
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
    <div class="flex shrink-0 items-center gap-0.5 opacity-60 group-hover:opacity-100">
      <button
        type="button"
        class="rounded bg-slate-700 px-1.5 py-1 text-[11px] text-slate-100 hover:bg-slate-600"
        :title="t('files.editTitle')"
        @click.stop="emit('edit', file.file_id)"
      >
        ✎
      </button>
      <button
        type="button"
        class="rounded bg-slate-700 px-1.5 py-1 text-[11px] text-slate-100 hover:bg-slate-600"
        :title="t('files.moveTo')"
        @click.stop="emit('move', file)"
      >
        📁
      </button>
      <button
        type="button"
        class="rounded text-slate-500 hover:text-red-300 px-1"
        :title="t('files.remove')"
        @click.stop="emit('remove', file)"
      >
        ✕
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
