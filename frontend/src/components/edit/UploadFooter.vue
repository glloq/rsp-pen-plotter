<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useFileManager } from '../../composables/useFileManager'
import { useBitmapDraft } from '../../composables/useBitmapDraft'
import { useJobStore } from '../../stores/job'

// Sticky bottom bar with the apply / upload button + preview-error /
// multipass-reupload warnings. Lives outside the tabs so the operator
// can apply changes from any tab — they're rarely back on the Colors
// tab when the conversion settings they tuned live in Render.
//
// The Apply button also surfaces the expected layer count so the
// operator knows the cost of their changes before committing.

const { t } = useI18n()
const fm = useFileManager(t)
const draft = useBitmapDraft()
const store = useJobStore()

// Only show the layer-count hint on the button when we're about to
// produce something (a bitmap source the operator hasn't applied yet)
// — adding it to the "Loading source file…" or "Converting…" states
// would be noise.
const showExpectedCount = computed(
  () => fm.showsBitmapForm.value && !store.loading && Boolean(fm.selectedFile.value),
)
</script>

<template>
  <div class="space-y-2 border-t border-slate-700 bg-slate-900/80 px-4 py-3 backdrop-blur">
    <div
      v-if="fm.hasSource.value && fm.previewError.value"
      class="rounded border border-red-700 bg-red-950/40 px-2 py-1 text-[11px] text-red-300"
    >
      <p>{{ fm.previewError.value }}</p>
      <div class="mt-1 flex flex-wrap gap-1">
        <button
          type="button"
          class="rounded border border-red-700 bg-red-900/60 px-2 py-0.5 text-[10px] text-red-100 hover:bg-red-800"
          @click="fm.previewer.retry"
        >
          {{ t('upload.retryPreview') }}
        </button>
        <span class="self-center text-[10px] text-red-300/80">
          {{ t('upload.applyAnywayHint') }}
        </span>
      </div>
    </div>

    <p
      v-if="fm.hasSource.value && fm.multiPassLayerCount.value > 0 && store.job"
      class="rounded border border-amber-700 bg-amber-950/40 px-2 py-1.5 text-[11px] text-amber-200"
    >
      ⚠ {{ t('passes.reuploadHint', { count: fm.multiPassLayerCount.value }) }}
    </p>

    <button
      v-if="fm.hasSource.value"
      type="button"
      class="w-full rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
      :disabled="store.loading || !fm.selectedFile.value"
      :title="!fm.selectedFile.value ? t('source.waitingForFile') : ''"
      @click="fm.uploadSelected"
    >
      {{
        !fm.selectedFile.value
          ? t('source.waitingForFile')
          : store.loading
            ? t('upload.converting')
            : store.job
              ? t('source.applyChanges')
              : t('upload.choose')
      }}
      <span
        v-if="showExpectedCount"
        class="ml-2 inline-block rounded-sm bg-emerald-800/80 px-1.5 py-px font-mono text-[10px] text-emerald-100"
        >→ {{ draft.expectedLayerCount.value }}
        {{ t('upload.layers', draft.expectedLayerCount.value) }}</span
      >
    </button>

    <p
      v-if="store.error && store.errorScope === 'upload'"
      class="rounded border border-red-700 bg-red-950/40 px-2 py-1 text-xs text-red-300"
    >
      {{ store.error }}
    </p>

    <ul
      v-if="store.uploadWarnings.length"
      class="rounded border border-amber-700 bg-amber-950/40 px-2 py-1.5 text-xs text-amber-200 space-y-0.5"
    >
      <li v-for="(warning, i) in store.uploadWarnings" :key="i">⚠ {{ warning }}</li>
    </ul>
  </div>
</template>
