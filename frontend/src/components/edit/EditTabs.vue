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
// instead of a tab.

export type EditTabId = 'image' | 'svg' | 'style' | 'text' | 'layers'

const props = defineProps<{
  modelValue: EditTabId
  layerCount: number
  showText: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: EditTabId): void
}>()

const { t } = useI18n()

interface TabSpec {
  id: EditTabId
  labelKey: string
  count?: number
  activeClass: string
  hoverClass: string
}

// Each tab has a distinct active colour so operators recognise context
// at a glance: Image=sky, SVG=amber, Style=violet, Text=rose,
// Layers=emerald. The Text tab is only present when the source carries
// text (typography or mixed text+image documents); bitmap-only sources
// keep the original 4-tab layout.
const tabs = computed<TabSpec[]>(() => {
  const list: TabSpec[] = [
    {
      id: 'image',
      labelKey: 'editModal.tabImage',
      activeClass: 'border-sky-600 bg-sky-950/60 text-sky-200',
      hoverClass: 'hover:border-sky-800 hover:text-sky-300',
    },
    {
      id: 'svg',
      labelKey: 'editModal.tabSvg',
      activeClass: 'border-amber-600 bg-amber-950/60 text-amber-200',
      hoverClass: 'hover:border-amber-800 hover:text-amber-300',
    },
    {
      id: 'style',
      labelKey: 'editModal.tabStyle',
      activeClass: 'border-violet-600 bg-violet-950/60 text-violet-200',
      hoverClass: 'hover:border-violet-800 hover:text-violet-300',
    },
  ]
  if (props.showText) {
    list.push({
      id: 'text',
      labelKey: 'editModal.tabText',
      activeClass: 'border-rose-600 bg-rose-950/60 text-rose-200',
      hoverClass: 'hover:border-rose-800 hover:text-rose-300',
    })
  }
  list.push({
    id: 'layers',
    labelKey: 'editModal.tabLayers',
    count: props.layerCount,
    activeClass: 'border-emerald-600 bg-emerald-950/60 text-emerald-200',
    hoverClass: 'hover:border-emerald-800 hover:text-emerald-300',
  })
  return list
})

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
      class="flex items-center gap-1.5 rounded border px-2.5 py-1 text-[11px] transition"
      :class="
        modelValue === tab.id
          ? tab.activeClass
          : ['border-slate-700 bg-slate-900 text-slate-400', tab.hoverClass]
      "
      @click="select(tab.id)"
    >
      <span>{{ t(tab.labelKey) }}</span>
      <span
        v-if="tab.count !== undefined && tab.count > 0"
        class="rounded-sm bg-slate-800 px-1 py-px font-mono text-[9px] text-slate-400"
        >{{ tab.count }}</span
      >
    </button>
  </div>
</template>
