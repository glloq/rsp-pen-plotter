<script setup lang="ts">
import { computed } from 'vue'
import draggable from 'vuedraggable'
import type { LayerInfo } from '../api/client'
import { useJobStore } from '../stores/job'
import LayerCard from './LayerCard.vue'

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
        Layers ({{ store.layers.length }})
      </h2>
      <span v-if="store.layers.length" class="text-xs text-slate-500">drag to reorder</span>
    </div>

    <p v-if="!store.layers.length" class="text-sm text-slate-500">No layers yet.</p>

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
        <span>Total length</span>
        <span class="font-mono">{{ store.totalLengthMm.toFixed(1) }} mm</span>
      </div>
      <div class="flex justify-between">
        <span>Estimated time</span>
        <span class="font-mono">{{ formatDuration(store.totalDurationSeconds) }}</span>
      </div>
    </div>
  </div>
</template>
