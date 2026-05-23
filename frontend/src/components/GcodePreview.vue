<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'

const { t } = useI18n()
const store = useJobStore()
const { gcode } = storeToRefs(store)

const lineCount = computed(() => (gcode.value ? gcode.value.split('\n').length : 0))

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
  <section v-if="gcode" class="flex h-full min-h-0 flex-col rounded-lg border border-slate-700 bg-slate-800/60">
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
    >{{ gcode }}</pre>
  </section>
</template>
