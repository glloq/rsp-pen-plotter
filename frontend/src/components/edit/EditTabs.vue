<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

// Tab strip for the modal's right-hand settings pane. Splits the long
// scrollable section into 3 contextual tabs (Source / Layers / Variants)
// so the operator reaches the right control with one click instead of
// scrolling through a 1000-line monolith.

export type EditTabId = 'source' | 'layers' | 'variants'

const props = defineProps<{
  modelValue: EditTabId
  layerCount: number
  variantCount: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: EditTabId): void
}>()

const { t } = useI18n()

interface TabSpec {
  id: EditTabId
  labelKey: string
  count?: number
  hint?: string
}

const tabs = computed<TabSpec[]>(() => [
  { id: 'source', labelKey: 'editModal.tabSource' },
  { id: 'layers', labelKey: 'editModal.tabLayers', count: props.layerCount },
  { id: 'variants', labelKey: 'variants.title', count: props.variantCount },
])

function select(id: EditTabId): void {
  emit('update:modelValue', id)
}
</script>

<template>
  <div
    role="tablist"
    class="sticky top-0 z-10 flex items-center gap-1 border-b border-slate-700 bg-slate-900/80 px-2 py-1.5 backdrop-blur"
  >
    <button
      v-for="tab in tabs"
      :key="tab.id"
      type="button"
      role="tab"
      :aria-selected="modelValue === tab.id"
      class="flex items-center gap-1 rounded border px-2.5 py-1 text-[11px] transition"
      :class="modelValue === tab.id
        ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
        : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600 hover:text-slate-100'"
      @click="select(tab.id)"
    >
      <span>{{ t(tab.labelKey) }}</span>
      <span
        v-if="tab.count !== undefined && tab.count > 0"
        class="rounded-sm bg-slate-800 px-1 py-px font-mono text-[9px] text-slate-400"
      >{{ tab.count }}</span>
    </button>
  </div>
</template>
