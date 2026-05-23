<script setup lang="ts">
import { computed } from 'vue'
import draggable from 'vuedraggable'
import { useI18n } from 'vue-i18n'
import type { LayerInfo } from '../api/client'
import { canReduceSwaps, groupByPen } from '../lib/penorder'
import { useJobStore } from '../stores/job'
import LayerCard from './LayerCard.vue'

const { t } = useI18n()
const store = useJobStore()

const draggableLayers = computed<LayerInfo[]>({
  get: () => store.layers,
  set: (value) => store.reorderLayers(value),
})

// Grouping by pen only matters when the machine has multiple pens to swap.
const canGroupByPen = computed(() => store.isMultiColor && canReduceSwaps(store.layers))

function groupLayersByPen(): void {
  store.reorderLayers(groupByPen(store.layers))
}
</script>

<template>
  <section v-if="store.layers.length" class="space-y-2">
    <div class="flex items-baseline justify-between px-1">
      <h2 class="text-xs uppercase tracking-wider text-slate-500">
        {{ t('layers.title') }} ({{ store.layers.length }})
      </h2>
      <span class="text-[10px] text-slate-600">{{ t('layers.dragHint') }}</span>
    </div>

    <button
      v-if="canGroupByPen"
      type="button"
      class="w-full rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
      @click="groupLayersByPen"
    >
      {{ t('layers.groupByPen') }}
    </button>

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
  </section>
</template>
