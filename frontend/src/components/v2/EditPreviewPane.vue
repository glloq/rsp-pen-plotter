<script setup lang="ts">
// Beginner-editor preview pane — extracted from EditModalV2 to keep
// that file under control as the modal accreted features.
//
// Encapsulates the SVG render surface, zoom/pan gesture vocabulary,
// the floating original ↔ plot toggle, the dashed sheet outline that
// shows paper proportions, and the gesture-hint footer line. All
// purely visual / interaction state stays local; the parent owns the
// adapted-render SVG, the original placement SVG, loading / error
// flags, and the sheet geometry, and just hands them down.

import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useProgressiveStream } from '../../composables/useProgressiveStream'
import { useJobStore } from '../../stores/job'

export interface SheetOutlineShape {
  widthPct: number
  heightPct: number
  labelW: number
  labelH: number
  isPortrait: boolean
}

const props = defineProps<{
  /** The adapted (resolver / custom-stack) render. May be null while
   *  the first preview is in flight. */
  plotSvg: string | null
  /** The original placement SVG, used as a fallback and as the target
   *  of the "Voir l'original" toggle. */
  originalSvg: string | null
  /** True while a /rerender is in flight — fades the displayed SVG. */
  loading: boolean
  /** True when the last render failed — surfaces a small message. */
  error: boolean
  /** Active sheet outline geometry, or null if no sheet is selected. */
  sheet: SheetOutlineShape | null
  /** Library file id of the active placement. When set AND a heavy
   *  preview is in flight, the pane opens an SSE connection to
   *  ``/preview/stream`` and surfaces layer-by-layer progress so the
   *  operator sees the pipeline advancing instead of an opaque spinner.
   *  Optional — when omitted, the pane falls back to the plain
   *  spinner. */
  streamFileId?: string | null
}>()

const { t } = useI18n()

// View mode: 'plot' = adapted render, 'original' = source placement.
// Hidden behind a button that only appears once both versions exist.
const viewMode = ref<'plot' | 'original'>('plot')
const canCompareOriginal = computed<boolean>(
  () => Boolean(props.originalSvg) && Boolean(props.plotSvg),
)
const displayedSvg = computed<string | null>(() => {
  if (viewMode.value === 'original') return props.originalSvg ?? props.plotSvg ?? null
  return props.plotSvg ?? props.originalSvg ?? null
})
function toggleViewMode(): void {
  viewMode.value = viewMode.value === 'plot' ? 'original' : 'plot'
}

// Zoom / pan — same gesture vocabulary as the rest of the app
// (wheel zooms, drag pans, double-click recentres). The view is
// intentionally *not* reset on prop changes so the operator can flip
// intent ↔ palette while zoomed into a detail.
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const panning = ref(false)
let panStartX = 0
let panStartY = 0
let panInitX = 0
let panInitY = 0
const MIN_ZOOM = 0.2
const MAX_ZOOM = 16

const contentStyle = computed(() => ({
  transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`,
  transformOrigin: 'center center',
  transition: panning.value ? 'none' : 'transform 0.08s ease-out',
}))

function clampZoom(value: number): number {
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, value))
}
function onWheel(event: WheelEvent): void {
  event.preventDefault()
  const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15
  zoom.value = clampZoom(zoom.value * factor)
}
function onPanStart(event: PointerEvent): void {
  if (event.button !== 0 && event.button !== 1) return
  panning.value = true
  panStartX = event.clientX
  panStartY = event.clientY
  panInitX = panX.value
  panInitY = panY.value
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}
function onPanMove(event: PointerEvent): void {
  if (!panning.value) return
  panX.value = panInitX + (event.clientX - panStartX)
  panY.value = panInitY + (event.clientY - panStartY)
}
function onPanEnd(event: PointerEvent): void {
  if (!panning.value) return
  panning.value = false
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
}
function zoomIn(): void {
  zoom.value = clampZoom(zoom.value * 1.25)
}
function zoomOut(): void {
  zoom.value = clampZoom(zoom.value / 1.25)
}
function resetView(): void {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
}

// =========================================================================
// Progressive preview stream (roadmap C.7 wiring).
// Opens an EventSource on /preview/stream while a heavy preview is in
// flight, and surfaces a percent + last-layer label inside the loading
// overlay. The composable cleans itself up onUnmounted and on
// done/error events, so the only thing the pane has to manage is the
// open/close lifecycle in response to the parent's loading flag.

const stream = useProgressiveStream()
const SLOW_PREVIEW_MS = 350
let openTimer: number | null = null

function shouldStream(): boolean {
  // Only open when we actually have a file id to stream from. Without
  // one the endpoint falls back to its synthetic emitter — not useful
  // here.
  return Boolean(props.streamFileId)
}

function clearOpenTimer(): void {
  if (openTimer !== null) {
    window.clearTimeout(openTimer)
    openTimer = null
  }
}

watch(
  () => props.loading,
  (loading) => {
    if (loading && shouldStream()) {
      // Don't fire the SSE for previews that resolve in < 350 ms —
      // opening + closing a connection for a fast render is wasted
      // work and the overlay flicker is annoying. The plain spinner
      // is fine for sub-second loads.
      clearOpenTimer()
      // Capture the file id at schedule time so a prop swap mid-delay
      // can't sneak ``undefined`` into the URL.
      const scheduledFileId = props.streamFileId
      openTimer = window.setTimeout(() => {
        openTimer = null
        // Re-check at fire time: the parent may have invalidated the
        // file (placement removed) during the 350 ms window. Bail
        // silently — the plain spinner is fine.
        if (!scheduledFileId || scheduledFileId !== props.streamFileId) return
        const url = `/preview/stream?file_id=${encodeURIComponent(scheduledFileId)}`
        stream.open(url)
      }, SLOW_PREVIEW_MS)
    } else {
      clearOpenTimer()
      stream.close()
    }
  },
)

// Vue auto-stops the watch on unmount, but a pending setTimeout would
// otherwise still fire — opening an EventSource after the composable's
// onUnmounted close already ran. Cancel the timer too so closing the
// modal mid-delay leaks nothing.
onBeforeUnmount(() => {
  clearOpenTimer()
})

// =========================================================================
// Per-layer opacity overlay (preview-only).
// The job store mutates ``layer.opacity_percent`` when the operator drags
// the LayerCard slider, but the backend's /rerender doesn't consume it —
// opacity is intentionally a *preview* hint, not a hardware parameter.
// We apply it client-side by walking the v-html'd SVG and setting
// ``stroke-opacity`` on each ``<g class="layer color-XXX">`` group, then
// re-apply whenever any layer's opacity_percent changes.

const job = useJobStore()
const previewRoot = ref<HTMLElement | null>(null)

function applyOpacityOverlay(): void {
  const root = previewRoot.value
  if (!root) return
  const svg = root.querySelector('svg')
  if (!svg) return
  // Build a layerId → opacity map so we can do one DOM walk instead of
  // N queries. Defaults the implicit 100 % case so groups whose layer
  // we don't recognise stay at 1.0 instead of inheriting a stale value
  // left over from a previous SVG.
  const opacityById = new Map<string, number>()
  for (const layer of job.layers) {
    const pct = layer.opacity_percent ?? 100
    opacityById.set(layer.layer_id, Math.max(0, Math.min(100, pct)) / 100)
  }
  // The bitmap / vector / text pipelines all label each per-layer
  // group with ``inkscape:label="color-XXXXXX"`` (= layer_id). The
  // namespaced attribute selector is fragile across parsers (HTML
  // vs XML mode), so we walk every <g> imperatively and filter on
  // the attribute presence. Reset to 1.0 when the group's layer
  // isn't in the active set so a stale value from the previous SVG
  // doesn't bleed through.
  const groups = svg.getElementsByTagName('g')
  for (const g of Array.from(groups)) {
    const label = g.getAttribute('inkscape:label')
    if (!label) continue
    const opacity = opacityById.get(label)
    g.style.opacity = opacity === undefined ? '1' : String(opacity)
  }
}

// Re-apply whenever the SVG content changes or any layer's
// opacity_percent value moves.
watch(
  () => [props.plotSvg, props.originalSvg, viewMode.value],
  () => {
    // The v-html commit happens during the same flush; defer to the
    // next microtask so the DOM is in place when we walk it.
    void Promise.resolve().then(applyOpacityOverlay)
  },
)
watch(
  () => job.layers.map((l) => `${l.layer_id}:${l.opacity_percent ?? 100}`).join('|'),
  () => applyOpacityOverlay(),
)

const streamLabel = computed<string>(() => {
  const payload = stream.lastProgress.value?.payload
  if (payload && typeof payload.layer_label === 'string') return payload.layer_label
  return ''
})
const streamPercent = computed<number>(() => stream.percent.value ?? 0)
const streamActive = computed<boolean>(() => Boolean(stream.active.value))
</script>

<template>
  <div>
    <div
      class="preview"
      data-test="modal-v2-preview"
      :style="{ cursor: panning ? 'grabbing' : 'grab', touchAction: 'none' }"
      @wheel="onWheel"
      @pointerdown="onPanStart"
      @pointermove="onPanMove"
      @pointerup="onPanEnd"
      @pointercancel="onPanEnd"
      @dblclick="resetView"
    >
      <div
        v-if="sheet"
        class="sheet-outline"
        :style="{
          width: `${sheet.widthPct}%`,
          height: `${sheet.heightPct}%`,
        }"
        aria-hidden="true"
        data-test="modal-v2-sheet-outline"
      >
        <span class="sheet-caption">
          {{ t('v2.modal.sheetCaptionLabel') }} ·
          {{ sheet.labelW }} × {{ sheet.labelH }} mm
        </span>
      </div>
      <div class="preview-viewport" :style="contentStyle">
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div
          v-if="displayedSvg"
          ref="previewRoot"
          class="preview-svg"
          :class="{ 'is-stale': loading }"
          data-test="modal-v2-preview-svg"
          v-html="displayedSvg"
        />
      </div>

      <button
        v-if="canCompareOriginal"
        type="button"
        class="view-toggle"
        :class="{ 'is-original': viewMode === 'original' }"
        :aria-pressed="viewMode === 'original'"
        data-test="modal-v2-view-toggle"
        @pointerdown.stop
        @wheel.stop
        @dblclick.stop
        @click="toggleViewMode"
      >
        {{ viewMode === 'plot' ? t('v2.modal.viewOriginal') : t('v2.modal.viewPlot') }}
      </button>

      <div
        class="zoom"
        data-test="modal-v2-zoom"
        @pointerdown.stop
        @wheel.stop
        @dblclick.stop
      >
        <button
          type="button"
          :title="t('v2.modal.zoomIn')"
          :aria-label="t('v2.modal.zoomIn')"
          data-test="modal-v2-zoom-in"
          @click="zoomIn"
        >
          +
        </button>
        <button
          type="button"
          :title="t('v2.modal.zoomOut')"
          :aria-label="t('v2.modal.zoomOut')"
          data-test="modal-v2-zoom-out"
          @click="zoomOut"
        >
          −
        </button>
        <button
          type="button"
          class="zoom-reset"
          :title="t('v2.modal.resetView')"
          :aria-label="t('v2.modal.resetView')"
          data-test="modal-v2-zoom-reset"
          @click="resetView"
        >
          {{ Math.round(zoom * 100) }}%
        </button>
      </div>

      <div
        v-if="loading"
        class="preview-overlay"
        role="status"
        aria-live="polite"
        data-test="modal-v2-preview-loading"
      >
        <span class="spinner" aria-hidden="true" />
        <span class="preview-overlay__label">
          {{ t('v2.modal.previewLoading') }}
          <span v-if="streamActive && streamLabel" class="preview-overlay__layer">
            · {{ streamLabel }}
          </span>
        </span>
        <!-- SSE progress bar: only shown when the stream is actually
             active. The percent comes straight from the backend
             ``progress`` events, so it tracks real pipeline state, not
             a fake loading animation. -->
        <div
          v-if="streamActive"
          class="preview-overlay__bar"
          role="progressbar"
          :aria-valuenow="streamPercent"
          aria-valuemin="0"
          aria-valuemax="100"
          data-test="modal-v2-preview-progress"
        >
          <div class="preview-overlay__bar-fill" :style="{ width: `${streamPercent}%` }" />
        </div>
      </div>
      <p v-if="error" class="preview-error" data-test="modal-v2-preview-error">
        {{ t('v2.modal.previewError') }}
      </p>
    </div>

    <p class="gesture-hint" data-test="modal-v2-gesture-hint">
      {{ t('v2.modal.gestureHint') }}
    </p>
  </div>
</template>

<style scoped>
.preview {
  position: relative;
  height: clamp(220px, 42vh, 360px);
  background: repeating-conic-gradient(#f1f5f9 0% 25%, white 0% 50%) 0 / 20px 20px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.preview-viewport {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  will-change: transform;
}
.preview-svg {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.5rem;
  transition: opacity 0.15s ease;
}
.preview-svg.is-stale {
  opacity: 0.45;
}
.preview-svg :deep(svg) {
  max-width: 100%;
  max-height: 100%;
  height: auto;
  width: auto;
}
.preview-overlay {
  position: absolute;
  inset: auto 0 0 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  padding: 0.5rem 0.75rem;
  background: rgba(255, 255, 255, 0.92);
  font-size: 0.8rem;
  color: #475569;
}
.preview-overlay__label {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.preview-overlay__layer {
  color: #1f6feb;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.72rem;
}
.preview-overlay__bar {
  width: min(100%, 240px);
  height: 4px;
  background: #e2e8f0;
  border-radius: 999px;
  overflow: hidden;
}
.preview-overlay__bar-fill {
  height: 100%;
  background: #1f6feb;
  border-radius: 999px;
  transition: width 0.15s ease;
}
.preview-error {
  position: absolute;
  inset: auto 0.5rem 0.5rem;
  margin: 0;
  text-align: center;
  font-size: 0.8rem;
  color: #b71c1c;
  background: #fdecea;
  padding: 0.35rem;
  border-radius: 4px;
}
.zoom {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.zoom button {
  width: 1.9rem;
  height: 1.9rem;
  border: 1px solid #cbd5e1;
  background: rgba(255, 255, 255, 0.92);
  color: #1e293b;
  border-radius: 4px;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.zoom button:hover {
  background: #e2e8f0;
}
.zoom button:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 2px;
}
.zoom-reset {
  font-size: 0.6rem !important;
  font-variant-numeric: tabular-nums;
}
.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #cbd5e1;
  border-top-color: #1f6feb;
  border-radius: 50%;
  animation: preview-spin 0.7s linear infinite;
}
@keyframes preview-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
  }
}

.sheet-outline {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 1px dashed #94a3b8;
  background: rgba(255, 255, 255, 0.4);
  border-radius: 2px;
  pointer-events: none;
  z-index: 0;
}
.sheet-caption {
  position: absolute;
  top: 2px;
  left: 4px;
  font-size: 0.6rem;
  color: #64748b;
  background: rgba(255, 255, 255, 0.7);
  padding: 0 3px;
  border-radius: 2px;
  font-variant-numeric: tabular-nums;
}

.view-toggle {
  position: absolute;
  bottom: 0.5rem;
  left: 0.5rem;
  padding: 0.25rem 0.65rem;
  border: 1px solid #cbd5e1;
  background: rgba(255, 255, 255, 0.92);
  color: #1e293b;
  border-radius: 999px;
  font-size: 0.72rem;
  cursor: pointer;
  z-index: 2;
}
.view-toggle:hover {
  background: white;
}
.view-toggle.is-original {
  background: #eef4ff;
  border-color: #1f6feb;
  color: #1f6feb;
}
.view-toggle:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 2px;
}

.gesture-hint {
  margin: 0.35rem 0 0;
  font-size: 0.7rem;
  color: #94a3b8;
  text-align: center;
  font-style: italic;
}
</style>
