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
</script>

<template>
  <div class="flex items-center gap-3 rounded border border-slate-700 bg-slate-800 px-3 py-2">
    <input v-model="visible" type="checkbox" class="h-4 w-4 accent-emerald-500" />
    <span
      class="h-5 w-5 rounded border border-slate-600 shrink-0"
      :style="{ backgroundColor: layer.source_color }"
    />
    <div class="min-w-0 flex-1">
      <p class="truncate font-mono text-sm text-slate-200">{{ layer.layer_id }}</p>
      <p class="text-xs text-slate-500">{{ layer.path_count }} paths</p>
    </div>
  </div>
</template>
