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
  <section class="space-y-2">
    <div class="flex items-baseline justify-between px-1">
      <h2 class="text-xs uppercase tracking-wider text-slate-500">
        {{ t('layers.title') }}<span v-if="store.layers.length"> ({{ store.layers.length }})</span>
      </h2>
      <span v-if="store.layers.length" class="text-[10px] text-slate-600">{{ t('layers.dragHint') }}</span>
    </div>

    <!-- Empty state: the section stays visible before conversion so the
         user knows where per-colour layer styles will land once the
         file is converted. -->
    <p
      v-if="!store.layers.length"
      class="rounded border border-dashed border-slate-700 bg-slate-900/40 px-3 py-2 text-[11px] text-slate-500"
    >
      {{ t('layers.emptyHint') }}
    </p>

    <button
      v-if="canGroupByPen"
      type="button"
      class="w-full rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
      @click="groupLayersByPen"
    >
      {{ t('layers.groupByPen') }}
    </button>

    <draggable
      v-if="store.layers.length"
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
