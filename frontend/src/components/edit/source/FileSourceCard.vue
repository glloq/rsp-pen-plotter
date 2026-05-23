<script setup lang="ts">
import { useI18n } from 'vue-i18n'

// File-picker card: shows either a compact summary of the currently
// attached file (the common case — the modal opens with a file 100%
// of the time) or a dashed dropzone for the rare empty-placement
// fallback. The hidden <input type=file> is delegated to the parent
// (SourceSection) so it can drive the picker programmatically and
// reuse the same accept list.

defineProps<{
  selectedFile: File | null
  kind: 'bitmap' | 'typography' | 'document' | 'none'
  hasJob: boolean
  dragOver: boolean
}>()

const emit = defineEmits<{
  (e: 'pick'): void
  (e: 'clear'): void
  (e: 'drop', file: File): void
  (e: 'update:dragOver', value: boolean): void
}>()

const { t } = useI18n()

function onDrop(event: DragEvent): void {
  emit('update:dragOver', false)
  const file = event.dataTransfer?.files?.[0] ?? null
  if (file) emit('drop', file)
}
</script>

<template>
  <section class="space-y-2">
    <div class="flex items-baseline justify-between px-1">
      <h2 class="text-xs uppercase tracking-wider text-slate-500">{{ t('prepare.source') }}</h2>
      <button
        v-if="selectedFile || hasJob"
        type="button"
        class="text-[10px] uppercase tracking-wider text-slate-500 hover:text-red-300"
        :title="t('upload.clear')"
        @click="emit('clear')"
      >
        ✕ {{ t('upload.clear') }}
      </button>
    </div>

    <div
      v-if="selectedFile"
      class="flex items-center gap-2 rounded border border-slate-700 bg-slate-900/60 px-2 py-1.5 text-xs"
    >
      <span class="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded bg-slate-800 text-[10px] text-slate-400" aria-hidden="true">
        {{ kind === 'bitmap' ? '🖼' : kind === 'typography' ? 'Aa' : '📄' }}
      </span>
      <div class="min-w-0 flex-1">
        <p class="truncate font-medium text-slate-100" :title="selectedFile.name">
          {{ selectedFile.name }}
        </p>
        <p class="text-[10px] text-slate-500">
          {{ (selectedFile.size / 1024).toFixed(1) }} KB · {{ kind }}
        </p>
      </div>
      <button
        type="button"
        class="shrink-0 rounded bg-slate-700 px-2 py-1 text-[10px] text-slate-100 hover:bg-slate-600"
        :title="t('upload.changeFile')"
        @click="emit('pick')"
      >
        {{ t('upload.changeFile') }}
      </button>
    </div>
    <div
      v-else
      class="rounded-lg border-2 border-dashed px-3 py-3 text-center transition"
      :class="dragOver ? 'border-emerald-500 bg-emerald-950/30' : 'border-slate-700 bg-slate-900/40'"
      @dragenter.prevent="emit('update:dragOver', true)"
      @dragover.prevent="emit('update:dragOver', true)"
      @dragleave.prevent="emit('update:dragOver', false)"
      @drop.prevent="onDrop"
    >
      <p class="text-sm text-slate-400">{{ t('upload.dropHere') }}</p>
      <button
        type="button"
        class="mt-2 rounded bg-slate-700 px-3 py-1 text-xs text-slate-100 hover:bg-slate-600"
        @click="emit('pick')"
      >
        {{ t('upload.pick') }}
      </button>
    </div>
  </section>
</template>
