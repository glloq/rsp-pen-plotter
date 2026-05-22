<script setup lang="ts">
import { computed } from 'vue'
import type { LayerInfo } from '../api/client'
import { useJobStore } from '../stores/job'

const props = defineProps<{ layer: LayerInfo }>()
const store = useJobStore()

const visible = computed({
  get: () => store.isVisible(props.layer.layer_id),
  set: (value: boolean) => store.setVisibility(props.layer.layer_id, value),
})

const penSlotCount = computed(() => store.selectedProfile?.pen_slot_count ?? 0)

function onPenSlot(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  store.updateLayer(props.layer.layer_id, { target_pen_slot: value === '' ? null : Number(value) })
}

function onSpeed(event: Event): void {
  const value = (event.target as HTMLInputElement).value
  store.updateLayer(props.layer.layer_id, {
    drawing_speed_mm_s: value === '' ? null : Number(value),
  })
}

function onSimplify(event: Event): void {
  store.updateLayer(props.layer.layer_id, {
    simplify_tolerance_mm: Number((event.target as HTMLInputElement).value),
  })
}

function onOptimize(event: Event): void {
  store.updateLayer(props.layer.layer_id, {
    optimize: (event.target as HTMLInputElement).checked,
  })
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs.toString().padStart(2, '0')}s`
}

const duration = computed(() => formatDuration(store.layerDurationSeconds(props.layer)))
</script>

<template>
  <div class="rounded border border-slate-700 bg-slate-800 px-3 py-2 space-y-2">
    <div class="flex items-center gap-3">
      <span class="cursor-grab text-slate-500 select-none" title="Drag to reorder">⠿</span>
      <input v-model="visible" type="checkbox" class="h-4 w-4 accent-emerald-500" />
      <span
        class="h-5 w-5 rounded border border-slate-600 shrink-0"
        :style="{ backgroundColor: layer.source_color }"
      />
      <div class="min-w-0 flex-1">
        <p class="truncate font-mono text-sm text-slate-200">{{ layer.layer_id }}</p>
        <p class="text-xs text-slate-500">
          {{ layer.path_count }} paths · {{ layer.total_length_mm.toFixed(1) }} mm · {{ duration }}
        </p>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-2 text-xs">
      <label class="text-slate-400">
        Pen slot
        <select
          :value="layer.target_pen_slot ?? ''"
          class="mt-0.5 w-full rounded bg-slate-900 border border-slate-700 px-1 py-0.5 text-slate-100"
          @change="onPenSlot"
        >
          <option value="">none</option>
          <option v-for="slot in penSlotCount" :key="slot" :value="slot - 1">
            {{ slot - 1 }}
          </option>
        </select>
      </label>
      <label class="text-slate-400">
        Speed (mm/s)
        <input
          type="number"
          min="1"
          :value="layer.drawing_speed_mm_s ?? ''"
          placeholder="default"
          class="mt-0.5 w-full rounded bg-slate-900 border border-slate-700 px-1 py-0.5 text-slate-100"
          @change="onSpeed"
        />
      </label>
      <label class="text-slate-400">
        Simplify (mm)
        <input
          type="number"
          min="0"
          step="0.01"
          :value="layer.simplify_tolerance_mm"
          class="mt-0.5 w-full rounded bg-slate-900 border border-slate-700 px-1 py-0.5 text-slate-100"
          @change="onSimplify"
        />
      </label>
      <label class="flex items-end gap-2 text-slate-400">
        <input
          type="checkbox"
          :checked="layer.optimize"
          class="h-4 w-4 accent-emerald-500"
          @change="onOptimize"
        />
        Optimize
      </label>
    </div>
  </div>
</template>
