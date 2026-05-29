<script setup lang="ts">
import { computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useUploadsStore } from '../stores/uploads'

const { t } = useI18n()
const uploads = useUploadsStore()
const { items, visible, active, total, doneCount, hasErrors, hasWarnings } = storeToRefs(uploads)

// Auto-dismiss a clean run: when every file landed without errors or
// warnings, the operator doesn't need to read or click anything, so the
// modal closes itself shortly after the batch settles. Runs with issues
// stay open until dismissed so the warnings/errors are actually seen.
let autoCloseTimer: ReturnType<typeof setTimeout> | null = null
watch(active, (running, was) => {
  if (autoCloseTimer) {
    clearTimeout(autoCloseTimer)
    autoCloseTimer = null
  }
  if (was && !running && !hasErrors.value && !hasWarnings.value) {
    autoCloseTimer = setTimeout(() => uploads.close(), 1200)
  }
})

const titleKey = computed(() => (active.value ? 'uploadModal.title' : 'uploadModal.titleDone'))

function labelFor(status: string): string {
  switch (status) {
    case 'uploading':
      return t('uploadModal.uploading')
    case 'converting':
      return t('uploadModal.converting')
    case 'done':
      return t('uploadModal.done')
    case 'existing':
      return t('uploadModal.existing')
    case 'error':
      return t('uploadModal.failed')
    case 'cancelled':
      return t('uploadModal.cancelled')
    default:
      return t('uploadModal.queued')
  }
}
</script>

<template>
  <div
    v-if="visible"
    class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
    aria-labelledby="upload-modal-title"
  >
    <div
      class="flex max-h-[80vh] w-full max-w-md flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-2xl"
      @click.stop
    >
      <div class="flex items-start gap-3">
        <span
          v-if="active"
          class="mt-1 inline-block h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-slate-600 border-t-emerald-400"
          aria-hidden="true"
        />
        <span
          v-else-if="hasErrors"
          class="mt-0.5 text-2xl leading-none text-red-400"
          aria-hidden="true"
          >✕</span
        >
        <span v-else class="mt-0.5 text-2xl leading-none text-emerald-400" aria-hidden="true"
          >✓</span
        >
        <div class="min-w-0 flex-1">
          <h2 id="upload-modal-title" class="text-base font-semibold text-slate-100">
            {{ t(titleKey) }}
          </h2>
          <p class="mt-1 text-sm text-slate-400">
            {{ t('uploadModal.summary', { done: doneCount, total }) }}
          </p>
        </div>
      </div>

      <ul class="mt-4 min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
        <li
          v-for="item in items"
          :key="item.id"
          class="rounded border border-slate-700/70 bg-slate-800/40 px-3 py-2"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="min-w-0 flex-1 truncate text-sm text-slate-200" :title="item.name">
              {{ item.name }}
            </span>
            <span
              class="shrink-0 text-xs font-medium"
              :class="{
                'text-emerald-400': item.status === 'done',
                'text-sky-300': item.status === 'existing',
                'text-red-400': item.status === 'error',
                'text-slate-400':
                  item.status === 'cancelled' ||
                  item.status === 'pending' ||
                  item.status === 'converting' ||
                  item.status === 'uploading',
              }"
            >
              <template v-if="item.status === 'uploading'">{{ item.percent }}%</template>
              <template v-else>{{ labelFor(item.status) }}</template>
            </span>
            <button
              v-if="
                item.status === 'uploading' ||
                item.status === 'converting' ||
                item.status === 'pending'
              "
              type="button"
              class="shrink-0 rounded px-1 text-slate-500 hover:text-slate-200"
              :title="t('uploadModal.cancelFile')"
              @click="uploads.cancelItem(item.id)"
            >
              ✕
            </button>
          </div>

          <!-- Network-transfer bar. Determinate while uploading, then a thin
               indeterminate pulse during the untimed server conversion. -->
          <div
            v-if="item.status === 'uploading' || item.status === 'converting'"
            class="mt-1.5 h-1 overflow-hidden rounded-full bg-slate-700"
          >
            <div
              v-if="item.status === 'uploading'"
              class="h-full rounded-full bg-emerald-500 transition-[width] duration-200"
              :style="{ width: `${item.percent}%` }"
            />
            <div v-else class="upload-indeterminate h-full rounded-full bg-emerald-500/70" />
          </div>

          <p
            v-if="item.warningCount > 0 && (item.status === 'done' || item.status === 'existing')"
            class="mt-1 text-[11px] text-amber-300"
          >
            ⚠ {{ t('uploadModal.warnings', { count: item.warningCount }, item.warningCount) }}
          </p>
        </li>
      </ul>

      <div class="mt-5 flex justify-end gap-2">
        <button
          v-if="active"
          type="button"
          class="rounded border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          @click="uploads.cancelAll()"
        >
          {{ t('uploadModal.cancelAll') }}
        </button>
        <button
          v-else
          type="button"
          class="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500"
          @click="uploads.close()"
        >
          {{ t('uploadModal.close') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Indeterminate sweep used while the server converts (no byte progress to
   report). Pure CSS so it costs nothing on the JS side. */
.upload-indeterminate {
  width: 40%;
  animation: upload-sweep 1.1s ease-in-out infinite;
}
@keyframes upload-sweep {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(250%);
  }
}
</style>
