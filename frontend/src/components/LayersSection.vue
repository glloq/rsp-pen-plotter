<script setup lang="ts">
import { computed, provide, ref, watch } from 'vue'
import draggable from 'vuedraggable'
import { useI18n } from 'vue-i18n'
import type { LayerInfo } from '../api/client'
import { canReduceSwaps, groupByPen } from '../lib/penorder'
import { useJobStore } from '../stores/job'
import { createLayerSelection, LayerSelectionKey } from '../composables/useLayerSelection'
import LayerCard from './LayerCard.vue'
import LayerBulkBar from './edit/LayerBulkBar.vue'

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
const canMergeToOnePen = computed(() => store.layers.some((l) => l.target_pen_slot !== 0))

function mergeToOnePen(): void {
  for (const layer of store.layers) {
    if (layer.target_pen_slot !== 0) {
      store.updateLayer(layer.layer_id, { target_pen_slot: 0 })
    }
  }
}

// Collapse-all toggle: 8+ layer placements are unscannable when every
// card is expanded. The cards read this injected ref and start
// collapsed when ``true``. ``null`` means each card keeps its own
// local toggle (the default before the section had this control).
const collapseAll = ref<boolean | null>(null)
provide<typeof collapseAll>('layersCollapseAll', collapseAll)

function setCollapseAll(value: boolean): void {
  collapseAll.value = value
}

// Multi-selection for bulk operations: click a layer header to select
// it, shift-click to extend the range, ctrl/⌘-click to toggle. The
// ``LayerBulkBar`` reads the same provided selection to expose the
// pen / style / reset-override bulk actions.
const selection = createLayerSelection()
provide(LayerSelectionKey, selection)
// Drop the selection whenever the layer set itself changes (re-upload,
// placement switch) so stale ids don't leak into bulk operations.
watch(
  () => store.layers.map((l) => l.layer_id).join(','),
  () => selection.clear(),
)

// Estimation footer for the layer set: total path length + duration so
// the operator sees the cost of the current layer choices at a glance.
function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  if (mins >= 60) {
    const hours = Math.floor(mins / 60)
    return `${hours}h ${(mins % 60).toString().padStart(2, '0')}m`
  }
  return `${mins}m ${secs.toString().padStart(2, '0')}s`
}

const totalLength = computed(() => store.layers.reduce((s, l) => s + l.total_length_mm, 0))
const totalDuration = computed(() =>
  store.layers.reduce((s, l) => s + store.layerDurationSeconds(l), 0),
)
const totalPaths = computed(() => store.layers.reduce((s, l) => s + l.path_count, 0))
</script>

<template>
  <section class="space-y-2">
    <div class="flex items-baseline justify-between px-1">
      <h2 class="text-xs uppercase tracking-wider text-slate-500">
        {{ t('layers.title') }}<span v-if="store.layers.length"> ({{ store.layers.length }})</span>
      </h2>
      <span v-if="store.layers.length" class="text-[10px] text-slate-600">{{
        t('layers.dragHint')
      }}</span>
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
      <button
        v-if="store.layers.length > 1"
        type="button"
        class="rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-[11px] text-slate-300 hover:bg-slate-800"
        :title="t('layers.expandAllHint')"
        @click="setCollapseAll(false)"
      >
        ▾ {{ t('layers.expandAll') }}
      </button>
      <button
        v-if="store.layers.length > 1"
        type="button"
        class="rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-[11px] text-slate-300 hover:bg-slate-800"
        :title="t('layers.collapseAllHint')"
        @click="setCollapseAll(true)"
      >
        ▸ {{ t('layers.collapseAll') }}
      </button>
    </div>

    <LayerBulkBar v-if="store.layers.length" />

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

    <!-- Summary footer: aggregated path count + length + duration for
         the active variant's visible layers. Lets the operator see the
         cost of their layer choices without leaving the modal. -->
    <div
      v-if="store.layers.length"
      class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded border border-slate-700 bg-slate-900/50 px-2 py-1.5 text-[10px] text-slate-400"
    >
      <span class="uppercase tracking-wider text-slate-500">{{ t('layers.summary') }}</span>
      <span>{{ totalPaths }} {{ t('layers.paths') }}</span>
      <span>·</span>
      <span>{{ totalLength.toFixed(0) }} mm</span>
      <span>·</span>
      <span>≈ {{ formatDuration(totalDuration) }}</span>
    </div>
  </section>
</template>
