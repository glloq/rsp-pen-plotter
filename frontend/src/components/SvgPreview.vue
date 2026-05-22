<script setup lang="ts">
import svgPanZoom from 'svg-pan-zoom'
import { onBeforeUnmount, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useJobStore } from '../stores/job'

const store = useJobStore()
const { svg, visibility } = storeToRefs(store)
const container = ref<HTMLDivElement | null>(null)
let panZoom: SvgPanZoom.Instance | null = null
let viewport: SVGElement | null = null

function applyVisibility(): void {
  const root = container.value?.querySelector('svg')
  if (!root) return
  const byLabel = new Map<string, SVGElement>()
  for (const group of Array.from(root.querySelectorAll('g'))) {
    const label = group.getAttribute('inkscape:label')
    if (label) byLabel.set(label, group)
  }
  for (const layer of store.layers) {
    const target = byLabel.get(layer.layer_id) ?? viewport
    if (target) {
      target.style.display = store.isVisible(layer.layer_id) ? '' : 'none'
    }
  }
}

function render(markup: string | null): void {
  if (panZoom) {
    panZoom.destroy()
    panZoom = null
  }
  if (!container.value) return
  container.value.innerHTML = markup ?? ''
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
}

watch(svg, (markup) => render(markup), { immediate: true })
watch(visibility, () => applyVisibility(), { deep: true })

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
    Upload a file to preview it here
  </div>
</template>
