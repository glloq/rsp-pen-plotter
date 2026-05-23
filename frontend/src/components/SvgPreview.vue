<script setup lang="ts">
import DOMPurify from 'dompurify'
import svgPanZoom from 'svg-pan-zoom'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'

const { t } = useI18n()
const store = useJobStore()
const { svg, visibility } = storeToRefs(store)
const container = ref<HTMLDivElement | null>(null)
let panZoom: SvgPanZoom.Instance | null = null
let viewport: SVGElement | null = null

function layerGroups(): Map<string, SVGElement> {
  const root = container.value?.querySelector('svg')
  const byLabel = new Map<string, SVGElement>()
  if (!root) return byLabel
  for (const group of Array.from(root.querySelectorAll('g'))) {
    const label = group.getAttribute('inkscape:label')
    if (label) byLabel.set(label, group)
  }
  return byLabel
}

function applyVisibility(): void {
  const byLabel = layerGroups()
  if (!byLabel.size && !viewport) return
  for (const layer of store.layers) {
    const target = byLabel.get(layer.layer_id) ?? viewport
    if (target) {
      target.style.display = store.isVisible(layer.layer_id) ? '' : 'none'
    }
  }
}

function applyPenColors(): void {
  const pens = store.selectedProfile?.pens ?? []
  const byLabel = layerGroups()
  for (const layer of store.layers) {
    const group = byLabel.get(layer.layer_id)
    if (!group) continue
    const color =
      layer.target_pen_slot === null
        ? null
        : (pens.find((p) => p.index === layer.target_pen_slot)?.color ?? null)
    if (!color) continue
    group.style.stroke = color
    for (const el of Array.from(group.querySelectorAll<SVGElement>('[stroke]'))) {
      if (el.getAttribute('stroke') !== 'none') el.style.stroke = color
    }
  }
}

function render(markup: string | null): void {
  if (panZoom) {
    panZoom.destroy()
    panZoom = null
  }
  if (!container.value) return
  container.value.innerHTML = markup
    ? DOMPurify.sanitize(markup, { USE_PROFILES: { svg: true, svgFilters: true } })
    : ''
  const root = container.value.querySelector('svg')
  if (!root) return
  root.setAttribute('width', '100%')
  root.setAttribute('height', '100%')
  panZoom = svgPanZoom(root, {
    controlIconsEnabled: true,
    fit: true,
    center: true,
  })
  viewport = container.value.querySelector<SVGElement>('.svg-pan-zoom_viewport')
  applyVisibility()
  applyPenColors()
}

// ``svg`` may turn truthy before the v-if-rendered container is in the DOM
// (Vue's flush isn't post by default), so defer rendering one tick to ensure
// ``container.value`` is bound — otherwise the SVG tab stays blank.
async function rerender(markup: string | null): Promise<void> {
  await nextTick()
  render(markup)
}

onMounted(() => rerender(svg.value))
watch(svg, (markup) => rerender(markup))
watch(visibility, () => applyVisibility(), { deep: true })
watch(
  () => store.layers.map((l) => l.target_pen_slot),
  () => applyPenColors(),
)
watch(() => store.selectedProfileName, () => applyPenColors())

onBeforeUnmount(() => panZoom?.destroy())
</script>

<template>
  <div
    v-if="svg"
    ref="container"
    class="h-[70vh] w-full rounded-lg border border-slate-700 bg-white overflow-hidden"
  />
  <div
    v-else
    class="h-[70vh] w-full rounded-lg border border-dashed border-slate-700 flex items-center justify-center text-slate-500"
  >
    {{ t('preview.placeholder') }}
  </div>
</template>
