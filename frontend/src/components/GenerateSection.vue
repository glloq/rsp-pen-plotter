<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'

const { t } = useI18n()
const store = useJobStore()

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs.toString().padStart(2, '0')}s`
}
</script>

<template>
  <section v-if="store.layers.length" class="space-y-2">
    <h2 class="px-1 text-xs uppercase tracking-wider text-slate-500">{{ t('prepare.output') }}</h2>

    <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2">
      <!--
        Optimize + preflight used to live here as opt-in buttons. They're
        now always-on: ``store.generate()`` runs the full pipeline
        (optimize → preflight → generate) and surfaces progress in the
        GenerateProgressModal. The results panels below are kept so the
        operator can still inspect the metrics after generation lands.
      -->
      <div
        v-if="store.metrics"
        class="rounded border border-sky-800 bg-sky-950/30 px-2 py-1.5 text-xs text-sky-200"
      >
        <div class="flex justify-between">
          <span>{{ t('layers.penUpTravel') }}</span>
          <span class="font-mono">
            {{ store.metrics.pen_up_before_mm.toFixed(0) }} →
            {{ store.metrics.pen_up_after_mm.toFixed(0) }} mm
          </span>
        </div>
        <div class="flex justify-between font-medium">
          <span>{{ t('layers.travelReduction') }}</span>
          <span class="font-mono">{{ store.metrics.reduction_pct.toFixed(1) }}%</span>
        </div>
      </div>

      <div
        v-if="store.preflight"
        class="rounded border px-2 py-1.5 text-xs"
        :class="
          store.preflight.ok
            ? 'border-emerald-800 bg-emerald-950/30 text-emerald-200'
            : 'border-amber-700 bg-amber-950/30 text-amber-200'
        "
      >
        <div class="flex justify-between">
          <span>{{ t('preflight.size') }}</span>
          <span class="font-mono">
            {{ store.preflight.width_mm.toFixed(0) }}×{{ store.preflight.height_mm.toFixed(0) }} mm
          </span>
        </div>
        <div class="flex justify-between">
          <span>{{ t('preflight.estimate') }}</span>
          <span class="font-mono">{{ formatDuration(store.preflight.estimated_seconds) }}</span>
        </div>
        <div class="flex justify-between">
          <span>{{ t('preflight.penChanges') }}</span>
          <span class="font-mono">{{ store.preflight.pen_changes }}</span>
        </div>
        <ul v-if="store.preflight.warnings.length" class="mt-1 list-disc pl-4">
          <li v-for="(warning, i) in store.preflight.warnings" :key="i">{{ warning }}</li>
        </ul>
      </div>

      <!-- Pre-generation guidance only: once metrics / preflight land
           the panel speaks for itself, so the hint would just be noise. -->
      <p
        v-if="!store.metrics && !store.preflight"
        class="rounded border border-slate-700 bg-slate-900/50 px-2 py-1 text-[11px] leading-snug text-slate-400"
      >
        {{ t('layers.generateHint') }}
      </p>

      <p
        v-if="store.error && (store.errorScope === 'optimize' || store.errorScope === 'generate')"
        class="rounded border border-red-700 bg-red-950/40 px-2 py-1 text-xs text-red-300"
      >
        {{ store.error }}
      </p>
    </div>
  </section>
</template>
