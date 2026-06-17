<script setup lang="ts">
// Reusable live camera preview: renders an MJPEG/HTTP stream (or a snapshot)
// from a URL with loading / error / empty states and a refresh button.
//
// Used by the Cameras settings tab — for each workshop camera and for the
// offset camera — so the operator can confirm a URL actually produces a feed.
//
// Optionally overlays the detection-zone (ROI) rectangle on the feed, mapped
// from source pixels onto the object-contain-scaled <img>. When `editable`,
// the operator can drag a new zone directly on the feed; the box is emitted
// (in source pixels) via `update:roi`.

import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

interface Roi {
  x: number
  y: number
  width: number
  height: number
}

const props = withDefaults(
  defineProps<{
    url: string
    label?: string
    height?: 'sm' | 'md'
    roi?: Roi | null
    // Allow dragging a new ROI rectangle directly on the feed.
    editable?: boolean
  }>(),
  { label: '', height: 'sm', roi: null, editable: false },
)

const emit = defineEmits<{ (e: 'update:roi', roi: Roi): void }>()

const { t } = useI18n()

const trimmed = computed(() => props.url.trim())
const errored = ref(false)
const nonce = ref(0)
const src = computed(() => {
  if (!trimmed.value) return ''
  const sep = trimmed.value.includes('?') ? '&' : '?'
  return nonce.value ? `${trimmed.value}${sep}_op=${nonce.value}` : trimmed.value
})

watch(trimmed, () => {
  errored.value = false
})

function refresh(): void {
  errored.value = false
  nonce.value = Date.now()
}

const heightClass = computed(() => (props.height === 'md' ? 'h-48' : 'h-28'))

// ── Geometry: map between source pixels and on-screen (object-contain) px ──
const containerEl = ref<HTMLElement | null>(null)
const imgEl = ref<HTMLImageElement | null>(null)
const natural = ref<{ w: number; h: number } | null>(null)
const box = ref<{ left: number; top: number; width: number; height: number } | null>(null)

interface Geom {
  scale: number
  offX: number
  offY: number
  rectLeft: number
  rectTop: number
}
function geom(): Geom | null {
  const container = containerEl.value
  if (!container || !natural.value || natural.value.w <= 0 || natural.value.h <= 0) return null
  const rect = container.getBoundingClientRect()
  const cw = rect.width
  const ch = rect.height
  if (cw <= 0 || ch <= 0) return null
  const scale = Math.min(cw / natural.value.w, ch / natural.value.h)
  if (scale <= 0) return null
  return {
    scale,
    offX: (cw - natural.value.w * scale) / 2,
    offY: (ch - natural.value.h * scale) / 2,
    rectLeft: rect.left,
    rectTop: rect.top,
  }
}

function computeBox(): void {
  const roi = props.roi
  const g = geom()
  if (!roi || !g) {
    box.value = null
    return
  }
  box.value = {
    left: g.offX + roi.x * g.scale,
    top: g.offY + roi.y * g.scale,
    width: roi.width * g.scale,
    height: roi.height * g.scale,
  }
}

function onLoad(): void {
  const img = imgEl.value
  if (img) natural.value = { w: img.naturalWidth, h: img.naturalHeight }
  void nextTick(computeBox)
}

watch(() => props.roi, computeBox, { deep: true })

let ro: ResizeObserver | undefined
watch(containerEl, (el) => {
  ro?.disconnect()
  if (el && typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => computeBox())
    ro.observe(el)
  }
})
onBeforeUnmount(() => ro?.disconnect())

// ── Drag-to-draw ROI ──────────────────────────────────────────────────────
const dragging = ref(false)
// Live box in container pixels while dragging.
const dragBox = ref<{ left: number; top: number; width: number; height: number } | null>(null)
let startLocal: { x: number; y: number } | null = null
let dragGeom: Geom | null = null

function localPoint(e: PointerEvent, g: Geom): { x: number; y: number } {
  return { x: e.clientX - g.rectLeft, y: e.clientY - g.rectTop }
}

function onPointerdown(e: PointerEvent): void {
  if (!props.editable) return
  const g = geom()
  if (!g) return
  dragGeom = g
  startLocal = localPoint(e, g)
  dragging.value = true
  dragBox.value = { left: startLocal.x, top: startLocal.y, width: 0, height: 0 }
  ;(e.target as Element).setPointerCapture?.(e.pointerId)
}

function onPointermove(e: PointerEvent): void {
  if (!dragging.value || !startLocal || !dragGeom) return
  const p = localPoint(e, dragGeom)
  dragBox.value = {
    left: Math.min(startLocal.x, p.x),
    top: Math.min(startLocal.y, p.y),
    width: Math.abs(p.x - startLocal.x),
    height: Math.abs(p.y - startLocal.y),
  }
}

function onPointerup(): void {
  if (!dragging.value || !dragBox.value || !dragGeom || !natural.value) {
    dragging.value = false
    dragBox.value = null
    return
  }
  const g = dragGeom
  // Container px → source px, clamped to the image bounds.
  const toSrc = (lpx: number, off: number, max: number) =>
    Math.round(Math.min(Math.max((lpx - off) / g.scale, 0), max))
  const x0 = toSrc(dragBox.value.left, g.offX, natural.value.w)
  const y0 = toSrc(dragBox.value.top, g.offY, natural.value.h)
  const x1 = toSrc(dragBox.value.left + dragBox.value.width, g.offX, natural.value.w)
  const y1 = toSrc(dragBox.value.top + dragBox.value.height, g.offY, natural.value.h)
  dragging.value = false
  dragBox.value = null
  dragGeom = null
  const width = x1 - x0
  const height = y1 - y0
  // Ignore a stray click / sub-pixel drag.
  if (width >= 2 && height >= 2) emit('update:roi', { x: x0, y: y0, width, height })
}
</script>

<template>
  <div
    ref="containerEl"
    class="relative flex items-center justify-center overflow-hidden rounded border border-slate-700 bg-black"
    :class="[heightClass, editable && trimmed && !errored ? 'cursor-crosshair' : '']"
    data-test="camera-preview"
    @pointerdown="onPointerdown"
    @pointermove="onPointermove"
    @pointerup="onPointerup"
  >
    <!-- Empty: no URL yet. -->
    <p
      v-if="!trimmed"
      class="px-2 text-center text-[11px] text-slate-500"
      data-test="preview-empty"
    >
      {{ t('cameraPreview.empty') }}
    </p>

    <!-- Error: the stream/snapshot failed to load. -->
    <div
      v-else-if="errored"
      class="flex flex-col items-center gap-1 px-2 text-center"
      data-test="preview-error"
    >
      <span aria-hidden="true">⚠️</span>
      <p class="text-[11px] text-red-300">{{ t('camera.streamError') }}</p>
      <button
        type="button"
        class="rounded border border-slate-600 px-2 py-0.5 text-[10px] text-slate-200 hover:bg-slate-700"
        data-test="preview-retry"
        @click="refresh"
      >
        {{ t('cameraPreview.retry') }}
      </button>
    </div>

    <!-- Live feed. -->
    <template v-else>
      <img
        :key="src"
        ref="imgEl"
        :src="src"
        :alt="label || t('camera.title')"
        class="max-h-full max-w-full select-none object-contain"
        draggable="false"
        data-test="preview-img"
        @load="onLoad"
        @error="errored = true"
      />
      <!-- Detection-zone overlay (stored ROI, or the live drag box). -->
      <div
        v-if="dragBox || box"
        class="pointer-events-none absolute border-2 border-emerald-400/80"
        :style="{
          left: (dragBox ?? box)!.left + 'px',
          top: (dragBox ?? box)!.top + 'px',
          width: (dragBox ?? box)!.width + 'px',
          height: (dragBox ?? box)!.height + 'px',
        }"
        data-test="preview-roi"
      />
      <span
        class="absolute left-1 top-1 flex items-center gap-1 rounded bg-black/50 px-1.5 py-0.5 text-[9px] font-medium text-emerald-300"
        data-test="preview-live"
      >
        <span class="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
        {{ t('camera.live') }}
      </span>
      <span
        v-if="editable"
        class="pointer-events-none absolute bottom-1 left-1 rounded bg-black/50 px-1.5 py-0.5 text-[9px] text-slate-300"
        data-test="preview-drag-hint"
      >
        {{ t('cameraPreview.dragHint') }}
      </span>
      <button
        type="button"
        class="absolute right-1 top-1 rounded bg-black/50 px-1.5 py-0.5 text-[10px] text-slate-200 hover:bg-black/70"
        :title="t('cameraPreview.refresh')"
        :aria-label="t('cameraPreview.refresh')"
        data-test="preview-refresh"
        @click="refresh"
      >
        ↻
      </button>
    </template>
  </div>
</template>
