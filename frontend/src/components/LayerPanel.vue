<script setup lang="ts">
import { computed } from 'vue'
import draggable from 'vuedraggable'
import { useI18n } from 'vue-i18n'
import type { LayerInfo } from '../api/client'
import { useJobStore } from '../stores/job'
import LayerCard from './LayerCard.vue'

const { t } = useI18n()
const store = useJobStore()

const draggableLayers = computed<LayerInfo[]>({
  get: () => store.layers,
  set: (value) => store.reorderLayers(value),
})

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs.toString().padStart(2, '0')}s`
}
</script>

<template>
  <div class="space-y-2">
    <div class="flex items-baseline justify-between">
      <h2 class="text-sm uppercase tracking-wide text-slate-400">
        {{ t('layers.title') }} ({{ store.layers.length }})
      </h2>
      <span v-if="store.layers.length" class="text-xs text-slate-500">
        {{ t('layers.dragHint') }}
      </span>
    </div>

    <p v-if="!store.layers.length" class="text-sm text-slate-500">{{ t('layers.empty') }}</p>

    <draggable
      v-model="draggableLayers"
      item-key="layer_id"
      handle=".cursor-grab"
      class="space-y-2"
    >
      <template #item="{ element }">
        <LayerCard :layer="element" />
      </template>
    </draggable>

    <div
      v-if="store.layers.length"
      class="mt-3 rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-300"
    >
      <div class="flex justify-between">
        <span>{{ t('layers.totalLength') }}</span>
        <span class="font-mono">{{ store.totalLengthMm.toFixed(1) }} mm</span>
      </div>
      <div class="flex justify-between">
        <span>{{ t('layers.estimatedTime') }}</span>
        <span class="font-mono">{{ formatDuration(store.totalDurationSeconds) }}</span>
      </div>
    </div>

    <button
      v-if="store.layers.length"
      type="button"
      class="w-full rounded bg-sky-600 hover:bg-sky-500 px-4 py-2 font-medium text-white disabled:opacity-50"
      :disabled="store.optimizing"
      @click="store.optimize()"
    >
      {{ store.optimizing ? t('layers.optimizing') : t('layers.optimizeButton') }}
    </button>

    <div
      v-if="store.layers.length"
      class="grid grid-cols-2 gap-2 rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
    >
      <label class="block text-slate-400">
        {{ t('job.scaleMode') }}
        <select
          v-model="store.scaleMode"
          class="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-slate-100"
        >
          <option value="fit">{{ t('job.scaleFit') }}</option>
          <option value="actual">{{ t('job.scaleActual') }}</option>
        </select>
      </label>
      <label class="block text-slate-400" :class="{ 'opacity-40': store.scaleMode !== 'fit' }">
        {{ t('job.margin') }}
        <input
          v-model.number="store.marginMm"
          type="number"
          step="any"
          min="0"
          :disabled="store.scaleMode !== 'fit'"
          class="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-2 py-1 text-slate-100"
        />
      </label>
    </div>

    <button
      v-if="store.layers.length"
      type="button"
      class="w-full rounded bg-emerald-600 hover:bg-emerald-500 px-4 py-2 font-medium text-white disabled:opacity-50"
      :disabled="store.generating"
      @click="store.generate()"
    >
      {{ store.generating ? t('layers.generating') : t('layers.generate') }}
    </button>

    <div
      v-if="store.metrics"
      class="rounded border border-sky-800 bg-sky-950/40 px-3 py-2 text-sm text-sky-200"
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
      <p class="mt-1 text-xs text-sky-400/80">{{ t('layers.fillHint') }}</p>
    </div>
  </div>
</template>
