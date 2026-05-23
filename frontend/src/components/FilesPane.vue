<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'

const { t } = useI18n()
const store = useJobStore()
const ui = useUiStore()

interface FileRow {
  id: string
  name: string
  size: number | null
  layerCount: number
}

// The data model currently holds one active job at a time, so the file
// list has either zero or one entry. We still render it as a list so the
// surface is ready when multi-file support lands without another layout
// reshuffle.
const files = computed<FileRow[]>(() => {
  const name = store.lastFile?.name ?? store.job?.source_file ?? null
  if (!name) return []
  return [
    {
      id: store.job?.job_id ?? 'draft',
      name,
      size: store.lastFile?.size ?? null,
      layerCount: store.layers.length,
    },
  ]
})

function openEditor(): void {
  ui.openEditModal()
}

function clearJob(): void {
  store.clearJob()
}

function formatSize(bytes: number | null): string {
  if (bytes === null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// Mark a file row as a drag source for the plan. The custom MIME tag
// lets SheetPreview distinguish file-row drags from OS file drops
// without leaking through to the window-level "import" handler.
function onDragStart(event: DragEvent, file: FileRow): void {
  if (!event.dataTransfer) return
  event.dataTransfer.setData('application/x-omniplot-file', file.id)
  event.dataTransfer.setData('text/plain', file.name)
  event.dataTransfer.effectAllowed = 'copyMove'
}
</script>

<template>
  <aside class="flex min-h-0 flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-900/40">
    <header class="flex items-center justify-between border-b border-slate-700 px-3 py-2">
      <h2 class="text-xs uppercase tracking-wider text-slate-500">{{ t('files.title') }}</h2>
      <button
        type="button"
        class="rounded bg-emerald-600 px-2 py-1 text-xs font-medium text-white hover:bg-emerald-500"
        @click="openEditor"
      >
        + {{ t('files.addFile') }}
      </button>
    </header>

    <div class="flex-1 overflow-y-auto p-3">
      <div
        v-if="!files.length"
        class="flex h-full flex-col items-center justify-center gap-2 text-center text-slate-500"
      >
        <div class="text-4xl text-slate-700" aria-hidden="true">📄</div>
        <p class="text-sm text-slate-300">{{ t('files.empty') }}</p>
        <p class="max-w-[220px] text-xs text-slate-600">{{ t('files.emptyHint') }}</p>
      </div>

      <ul v-else class="space-y-2">
        <li
          v-for="file in files"
          :key="file.id"
          class="rounded border border-slate-700 bg-slate-800 px-3 py-2 cursor-grab active:cursor-grabbing"
          draggable="true"
          :title="t('files.dragHint')"
          @dragstart="(e) => onDragStart(e, file)"
        >
          <div class="flex items-start gap-2">
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium text-slate-100" :title="file.name">
                {{ file.name }}
              </p>
              <p class="text-[10px] text-slate-500">
                <span v-if="file.size !== null">{{ formatSize(file.size) }}</span>
                <span v-if="file.size !== null" class="text-slate-700"> · </span>
                <span v-if="file.layerCount">
                  {{ file.layerCount }} {{ t('upload.layers', file.layerCount) }}
                </span>
                <span v-else class="italic text-slate-600">{{ t('files.noLayers') }}</span>
              </p>
            </div>
            <button
              type="button"
              class="rounded bg-slate-700 px-2 py-1 text-[11px] text-slate-100 hover:bg-slate-600"
              :title="t('files.editTitle')"
              @click="openEditor"
            >
              ✎ {{ t('files.edit') }}
            </button>
            <button
              type="button"
              class="rounded text-slate-500 hover:text-red-300"
              :title="t('files.remove')"
              @click="clearJob"
            >
              ✕
            </button>
          </div>
        </li>
      </ul>
    </div>
  </aside>
</template>
