<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'

const { t } = useI18n()
const store = useJobStore()
const { gcode } = storeToRefs(store)

// Cap how many lines we inject into the live <pre>. A full plot can be
// hundreds of thousands of lines; rendering the whole string as one DOM
// text node was a layout/paint spike on open (audit B7). The operator
// never reads past the top anyway — the Download button (and the
// Simulator tab) cover the full program.
const MAX_PREVIEW_LINES = 2000
const lines = computed(() => (gcode.value ? gcode.value.split('\n') : []))
const lineCount = computed(() => lines.value.length)
const truncated = computed(() => lines.value.length > MAX_PREVIEW_LINES)
const previewText = computed(() =>
  truncated.value ? lines.value.slice(0, MAX_PREVIEW_LINES).join('\n') : (gcode.value ?? ''),
)

function download(): void {
  if (!gcode.value) return
  const blob = new Blob([gcode.value], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const base = (store.job?.source_file ?? 'output').replace(/\.[^.]+$/, '')
  const link = document.createElement('a')
  link.href = url
  link.download = `${base}.gcode`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <section
    v-if="gcode"
    class="flex h-full min-h-0 flex-col rounded-lg border border-slate-700 bg-slate-800/60"
  >
    <div class="flex items-center justify-between border-b border-slate-700 px-4 py-2">
      <h2 class="text-sm uppercase tracking-wide text-slate-400">
        {{ t('gcode.title') }} ({{ lineCount }} {{ t('gcode.lines') }})
      </h2>
      <button
        type="button"
        class="rounded bg-slate-700 hover:bg-slate-600 px-3 py-1 text-sm text-slate-100"
        @click="download"
      >
        {{ t('gcode.download') }}
      </button>
    </div>
    <pre
      class="min-h-0 flex-1 overflow-auto p-4 text-xs font-mono text-emerald-200 whitespace-pre"
      >{{ previewText }}</pre
    >
    <p v-if="truncated" class="border-t border-slate-700 px-4 py-1.5 text-[11px] text-slate-400">
      {{ t('gcode.truncated', { count: MAX_PREVIEW_LINES }) }}
    </p>
  </section>
</template>
