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

// One-click "single pen" remap: send every layer to pen slot 0 so the
// whole drawing prints in one ink, without re-uploading. Useful when
// the user picked multi-colour at upload but then realised they only
// have one pen to swap manually.
const canMergeToOnePen = computed(
  () => store.layers.some((l) => l.target_pen_slot !== 0),
)

function mergeToOnePen(): void {
  for (const layer of store.layers) {
    if (layer.target_pen_slot !== 0) {
      store.updateLayer(layer.layer_id, { target_pen_slot: 0 })
    }
  }
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

    <div v-if="store.layers.length" class="flex flex-wrap gap-1">
      <button
        v-if="canGroupByPen"
        type="button"
        class="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-[11px] text-slate-300 hover:bg-slate-800"
        @click="groupLayersByPen"
      >
        {{ t('layers.groupByPen') }}
      </button>
      <button
        v-if="canMergeToOnePen"
        type="button"
        class="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-[11px] text-slate-300 hover:bg-slate-800"
        :title="t('layers.mergeToOnePenHint')"
        @click="mergeToOnePen"
      >
        {{ t('layers.mergeToOnePen') }}
      </button>
    </div>

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
