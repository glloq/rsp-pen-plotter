<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

// Tab strip for the modal's right-hand settings pane. Splits the long
// scrollable section into 5 contextual tabs (Source / Colors / Render
// / Layers / Variants) ordered by the natural workflow: pick the
// source → segment into colours → choose how to render them → tune
// per-layer → snapshot a variant. The 5th tab moves to a persistent
// VariantsBar in Phase 4; for now it stays here so the migration
// happens in one self-contained UI step at a time.

export type EditTabId = 'source' | 'colors' | 'render' | 'layers' | 'variants'

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
  shortcut: string
  count?: number
}

// Shortcut keys mirror the global handler in EditModal.vue (the digits
// 1-5). The labelled <kbd> badge below makes them discoverable
// without forcing the operator to memorise an undocumented binding.
const tabs = computed<TabSpec[]>(() => [
  { id: 'source', labelKey: 'editModal.tabSource', shortcut: '1' },
  { id: 'colors', labelKey: 'editModal.tabColors', shortcut: '2' },
  { id: 'render', labelKey: 'editModal.tabRender', shortcut: '3' },
  { id: 'layers', labelKey: 'editModal.tabLayers', shortcut: '4', count: props.layerCount },
  { id: 'variants', labelKey: 'variants.title', shortcut: '5', count: props.variantCount },
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
      :title="t('editModal.tabShortcut', { key: tab.shortcut })"
      class="flex items-center gap-1.5 rounded border px-2.5 py-1 text-[11px] transition"
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
      <kbd
        class="hidden rounded border border-slate-700 bg-slate-950 px-1 font-mono text-[9px] text-slate-500 sm:inline"
        aria-hidden="true"
      >{{ tab.shortcut }}</kbd>
    </button>
  </div>
</template>
