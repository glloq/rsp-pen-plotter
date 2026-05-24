<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

// Tab strip for the modal's right-hand settings pane. Four workflow
// tabs: Image → SVG → Style → Layers. ``Image`` is the photo-editor
// step (brightness / contrast / crop / etc.) applied before the
// bitmap is segmented; it lives first so the operator preps the source
// pixels before anything downstream cares about colour count or
// rendering algorithm. ``SVG`` owns every technical knob that drives
// the image → SVG conversion (detail tier, centerline mode, curve
// simplification, segmentation method). ``Style`` merges the former
// Colors and Render tabs into a single surface focused on what the
// rendered output actually looks like (master style, palette, post-
// process filters). The old "Source" tab is gone — the modal always
// opens with a file already attached (Edit on a library entry); the
// rare empty-placement case shows a dedicated overlay dropzone
// instead of a tab. Variants live in the persistent VariantsBar
// mounted above this strip.

export type EditTabId = 'image' | 'svg' | 'style' | 'layers'

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
// 1-4). The labelled <kbd> badge below makes them discoverable
// without forcing the operator to memorise an undocumented binding.
const tabs = computed<TabSpec[]>(() => [
  { id: 'image', labelKey: 'editModal.tabImage', shortcut: '1' },
  { id: 'svg', labelKey: 'editModal.tabSvg', shortcut: '2' },
  { id: 'style', labelKey: 'editModal.tabStyle', shortcut: '3' },
  { id: 'layers', labelKey: 'editModal.tabLayers', shortcut: '4', count: props.layerCount },
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
