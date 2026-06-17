<script setup lang="ts">
// Reusable live camera preview: renders an MJPEG/HTTP stream (or a snapshot)
// from a URL with loading / error / empty states and a refresh button.
//
// Used by the Cameras settings tab — for each workshop camera and for the
// offset camera — so the operator can confirm a URL actually produces a feed
// before relying on it. Hardware-agnostic: a plain <img> renders an MJPEG
// stream as a live feed and a snapshot endpoint as a still.
//
// Optionally overlays the detection-zone (ROI) rectangle on the feed so the
// operator can see exactly where the offset detector will look — mapped from
// source pixels onto the object-contain-scaled <img>.

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
    // Compact height for inline previews; taller for a focused view.
    height?: 'sm' | 'md'
    // Detection zone in source pixels; drawn as an overlay when set.
    roi?: Roi | null
  }>(),
  { label: '', height: 'sm', roi: null },
)

const { t } = useI18n()

const trimmed = computed(() => props.url.trim())
const errored = ref(false)
// Cache-buster so "refresh" re-pulls a snapshot URL (and restarts a stalled
// MJPEG stream) without the operator editing the URL.
const nonce = ref(0)
const src = computed(() => {
  if (!trimmed.value) return ''
  const sep = trimmed.value.includes('?') ? '&' : '?'
  return nonce.value ? `${trimmed.value}${sep}_op=${nonce.value}` : trimmed.value
})

// A changed URL deserves a fresh attempt.
watch(trimmed, () => {
  errored.value = false
})

function refresh(): void {
  errored.value = false
  nonce.value = Date.now()
}

const heightClass = computed(() => (props.height === 'md' ? 'h-48' : 'h-28'))

// ── ROI overlay ───────────────────────────────────────────────────────────
const containerEl = ref<HTMLElement | null>(null)
const imgEl = ref<HTMLImageElement | null>(null)
const natural = ref<{ w: number; h: number } | null>(null)
const box = ref<{ left: number; top: number; width: number; height: number } | null>(null)

function computeBox(): void {
  const roi = props.roi
  const img = imgEl.value
  const container = containerEl.value
  if (!roi || !natural.value || !container || natural.value.w <= 0 || natural.value.h <= 0) {
    box.value = null
    return
  }
  const cw = container.clientWidth
  const ch = container.clientHeight
  // object-contain: the image is scaled uniformly and letter-boxed.
  const scale = Math.min(cw / natural.value.w, ch / natural.value.h)
  const renderedW = natural.value.w * scale
  const renderedH = natural.value.h * scale
  const offX = (cw - renderedW) / 2
  const offY = (ch - renderedH) / 2
  box.value = {
    left: offX + roi.x * scale,
    top: offY + roi.y * scale,
    width: roi.width * scale,
    height: roi.height * scale,
  }
  void img // keep the ref reactive dependency explicit
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
</script>

<template>
  <div
    ref="containerEl"
    class="relative flex items-center justify-center overflow-hidden rounded border border-slate-700 bg-black"
    :class="heightClass"
    data-test="camera-preview"
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
        class="max-h-full max-w-full object-contain"
        data-test="preview-img"
        @load="onLoad"
        @error="errored = true"
      />
      <!-- Detection-zone overlay. -->
      <div
        v-if="box"
        class="pointer-events-none absolute border-2 border-emerald-400/80"
        :style="{
          left: box.left + 'px',
          top: box.top + 'px',
          width: box.width + 'px',
          height: box.height + 'px',
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
