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

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEstimatedProgress } from '../../composables/useEstimatedProgress'
import { useProgressiveStream } from '../../composables/useProgressiveStream'
import { useJobStore } from '../../stores/job'

export interface SheetOutlineShape {
  // Real aspect ratio (w/h) — fed straight to CSS ``aspect-ratio`` so
  // the rectangle keeps its shape regardless of how wide vs. tall the
  // preview pane is. Percent-of-axis sizing distorted the shape on
  // non-square panes; that bug is what this interface fixes.
  aspectRatio: number
  labelW: number
  labelH: number
  isPortrait: boolean
  /** Real sheet width in mm — used to scale the artwork so the same
   *  drawing visibly shrinks when the operator picks a bigger paper
   *  format (and overflows when picking a smaller one). */
  widthMm: number
  /** Real sheet height in mm — companion to ``widthMm``. */
  heightMm: number
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
  /** Artwork's physical dimensions in mm. Used together with
   *  ``sheet.widthMm`` / ``heightMm`` to scale the SVG so it sits
   *  inside the chosen paper format at its real footprint instead
   *  of stretching to fill the pane. Omitted → fall back to the
   *  legacy "fit to pane" behaviour for documents that don't carry
   *  physical dimensions yet. */
  artworkWidthMm?: number | null
  artworkHeightMm?: number | null
  /** URL of the raw source image (PNG / JPG / PDF page raster / …),
   *  shown in the "Original" and "Compare" modes instead of the
   *  placement SVG. ``props.originalSvg`` was always the LAST
   *  converted SVG, so comparing against it just stacked two
   *  converted versions — the operator wanted to see the actual
   *  uploaded picture vs. the conversion. Optional; when omitted
   *  the pane falls back to ``originalSvg``. */
  sourceImageUrl?: string | null
  /** Expected /preview latency in ms for the active algorithm ×
   *  quality (from ``usePreviewCostEstimator``). Drives the estimated
   *  progress bar in the loading overlay; when the SSE stream reports
   *  real per-layer percents too, the bar shows whichever is further
   *  along. Optional — omitted falls back to a generic estimate. */
  estimateMs?: number | null
}>()

const { t } = useI18n()

// View mode: 'plot' = adapted render, 'source' = source placement,
// 'split' = compare slider that wipes between source and plot. The
// V1 modal had this three-way toggle; restoring it lets the operator
// verify what the conversion did to the photo without leaving the
// modal.
type PreviewMode = 'plot' | 'source' | 'split'
const viewMode = ref<PreviewMode>('plot')
// Both "Original" and "Compare" are usable as long as we have either a
// raw source image URL or the legacy fallback SVG. The image takes
// priority in the template — see ``hasSource`` below.
const hasSource = computed<boolean>(
  () => Boolean(props.sourceImageUrl) || Boolean(props.originalSvg),
)
const canShowOriginal = computed<boolean>(() => hasSource.value)
const canCompareOriginal = computed<boolean>(() => hasSource.value && Boolean(props.plotSvg))
function setMode(mode: PreviewMode): void {
  if (mode === 'source' && !canShowOriginal.value) return
  if (mode === 'split' && !canCompareOriginal.value) return
  viewMode.value = mode
}
// The legacy single-button toggle is gone; the template renders a
// three-way Result / Source / Compare segmented control instead.

// Pick which SVG the standalone Result / Source modes show; Split mode
// stacks both so it consumes the props directly in the template.
const displayedSvg = computed<string | null>(() => {
  if (viewMode.value === 'source') return props.originalSvg ?? props.plotSvg ?? null
  return props.plotSvg ?? props.originalSvg ?? null
})

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
// Sheet outline sizing.
// CSS ``aspect-ratio`` alone won't fit a rectangle into a non-square
// pane without distortion — when both axes are constrained, the
// browser picks one and the aspect breaks. We track the pane's real
// pixel size with ResizeObserver, then derive the sheet's width/height
// in pixels so it's *guaranteed* to honour the requested aspect ratio
// AND fit inside 92 % of the pane on whichever axis is tighter.
const paneEl = ref<HTMLElement | null>(null)
const paneWidth = ref(0)
const paneHeight = ref(0)
let paneObserver: ResizeObserver | null = null

const sheetStyle = computed<{ width: string; height: string } | null>(() => {
  const s = props.sheet
  if (!s) return null
  const ratio = s.aspectRatio
  if (!Number.isFinite(ratio) || ratio <= 0) return null
  const pw = paneWidth.value
  const ph = paneHeight.value
  if (pw <= 0 || ph <= 0) return null
  const maxW = pw * 0.92
  const maxH = ph * 0.92
  // Anchor on whichever axis caps the rectangle first. ``maxW / ratio``
  // is the height the rectangle would take if it filled maxW; if that
  // exceeds maxH, the sheet is taller than it is wide and we anchor
  // on height instead.
  let w: number
  let h: number
  if (maxW / ratio <= maxH) {
    w = maxW
    h = maxW / ratio
  } else {
    h = maxH
    w = maxH * ratio
  }
  return { width: `${Math.round(w)}px`, height: `${Math.round(h)}px` }
})

// =========================================================================
// Artwork-inside-sheet sizing.
// The previous layout rendered the SVG and the sheet outline as
// independent overlays — picking A4 vs. A3 left the artwork at the
// same on-screen size and made it overflow the paper. The fix sizes
// the artwork as a fraction of the sheet (artworkMm / sheetMm), so a
// 100 × 100 mm drawing visibly fills half of an A4 portrait (210
// × 297 mm) and barely covers a quarter of A3. Falls back to "fill the
// sheet" when the artwork's own dimensions aren't known yet (typically
// during the first /preview round-trip on upload).
const artworkStyle = computed<{ width: string; height: string } | null>(() => {
  if (!props.sheet) return null
  const sw = props.sheet.widthMm
  const sh = props.sheet.heightMm
  if (!sw || !sh) return null
  const aw = props.artworkWidthMm ?? sw
  const ah = props.artworkHeightMm ?? sh
  // Express the artwork box as a percentage of the sheet so the inline
  // sheet container (already sized in pixels by ``sheetStyle``) does
  // the unit conversion for us. Clamp at 100 % so an artwork bigger
  // than the sheet doesn't bleed into the surrounding pane — instead
  // it visibly fills the sheet and the rest of the artwork sits behind
  // the overflow boundary (operator can see the clipping in the
  // dashed sheet border).
  const wPct = Math.min(100, (aw / sw) * 100)
  const hPct = Math.min(100, (ah / sh) * 100)
  return { width: `${wPct}%`, height: `${hPct}%` }
})

// =========================================================================
// Split / compare slider.
// V1 had a vertical reveal: dragging the handle swept between the
// source preview (left half) and the converted result (right half).
// V2 inherits the same mechanic so the operator can verify what the
// algorithm did to the photo without leaving the modal.
const splitPercent = ref<number>(50)
const splitDragging = ref<boolean>(false)
// We measure against the SHEET, not the pane, because the handle's
// ``left: ${splitPercent}%`` is relative to the sheet outline (which
// is what contains the artwork). Using the pane rect made the handle
// jump under the pointer when the sheet wasn't pane-wide.
let splitSheetRect: DOMRect | null = null

function onSplitGrab(event: PointerEvent): void {
  const sheet = (event.currentTarget as HTMLElement).closest('.sheet-outline') as HTMLElement | null
  if (!sheet) return
  event.stopPropagation()
  event.preventDefault()
  splitDragging.value = true
  splitSheetRect = sheet.getBoundingClientRect()
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  updateSplit(event)
}
function onSplitMove(event: PointerEvent): void {
  if (!splitDragging.value) return
  updateSplit(event)
}
function onSplitRelease(event: PointerEvent): void {
  if (!splitDragging.value) return
  splitDragging.value = false
  splitSheetRect = null
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
}
function updateSplit(event: PointerEvent): void {
  if (!splitSheetRect) return
  const x = event.clientX - splitSheetRect.left
  const pct = (x / splitSheetRect.width) * 100
  splitPercent.value = Math.max(0, Math.min(100, pct))
}

// Reset to 50/50 when switching INTO split mode so the operator gets a
// clean fresh sweep instead of inheriting wherever the last drag ended
// (often 0 % or 100 %, which hides one side entirely).
watch(viewMode, (next, prev) => {
  if (next === 'split' && prev !== 'split') splitPercent.value = 50
})

// Clip-paths for the split mode: the plot SVG is revealed from the
// right edge inward to ``splitPercent``; the source SVG is shown only
// in the complementary left band. Implemented with ``clip-path`` so
// each half stays at full opacity and stacking is just z-order.
const splitPlotClip = computed<string>(() => `inset(0 0 0 ${splitPercent.value}%)`)
const splitSourceClip = computed<string>(() => `inset(0 ${100 - splitPercent.value}% 0 0)`)

onMounted(() => {
  if (!paneEl.value || typeof ResizeObserver === 'undefined') return
  paneObserver = new ResizeObserver((entries) => {
    const entry = entries[0]
    if (!entry) return
    const rect = entry.contentRect
    paneWidth.value = rect.width
    paneHeight.value = rect.height
  })
  paneObserver.observe(paneEl.value)
})

onBeforeUnmount(() => {
  paneObserver?.disconnect()
  paneObserver = null
})

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

// Estimated determinate progress — always available while loading,
// even when no SSE stream can run (draft previews without a library
// file id, single-band mono renders whose stream would tick 0→100 in
// one step). When the stream *is* reporting, the bar shows whichever
// of the two is further along so real layer ticks can only move it
// forward, never backwards.
const estimatedProgress = useEstimatedProgress(
  () => props.loading,
  () => props.estimateMs ?? 0,
)
const displayPercent = computed<number>(() =>
  streamActive.value
    ? Math.max(streamPercent.value, estimatedProgress.percent.value)
    : estimatedProgress.percent.value,
)
</script>

<template>
  <div class="preview-pane">
    <div
      ref="paneEl"
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
      <!-- Zoom/pan stage. Centres the sheet (or the legacy
           unbounded SVG fallback) inside the pane and applies the
           ``contentStyle`` transform so wheel/drag gestures still
           work after the artwork moved inside the sheet rectangle. -->
      <div class="preview-stage" :style="contentStyle">
        <!-- Sheet-as-canvas: the artwork lives INSIDE the dashed
             rectangle now, so picking a bigger paper visibly shrinks
             the drawing and picking a smaller one makes it overflow
             the border. Drops back to "fill the pane" when no sheet
             is selected so the operator still sees something. -->
        <div
          v-if="sheet && sheetStyle"
          class="sheet-outline"
          :style="sheetStyle"
          data-test="modal-v2-sheet-outline"
        >
          <span class="sheet-caption" aria-hidden="true">
            {{ t('v2.modal.sheetCaptionLabel') }} · {{ sheet.labelW }} × {{ sheet.labelH }} mm
          </span>
          <!-- Artwork box sized as a percentage of the sheet so its
               footprint reflects the drawing's real mm size. -->
          <div
            v-if="artworkStyle"
            ref="previewRoot"
            class="artwork-box"
            :style="artworkStyle"
            data-test="modal-v2-artwork-box"
          >
            <!-- Plot (result) layer — always rendered; split mode
                 clips it from the left so the source shows on that
                 side. -->
            <!-- eslint-disable-next-line vue/no-v-html -->
            <div
              v-if="props.plotSvg"
              class="artwork-svg artwork-svg--plot"
              :class="{ 'is-stale': loading, 'is-hidden': viewMode === 'source' }"
              :style="viewMode === 'split' ? { clipPath: splitPlotClip } : {}"
              data-test="modal-v2-preview-svg"
              v-html="props.plotSvg"
            />
            <!-- Source (original) layer — rendered only when needed so
                 the DOM stays light when the operator is on plot-only.
                 Prefers the raw source image (``sourceImageUrl``) so
                 "Compare" shows the actual uploaded photo vs. the
                 converted result. Falls back to ``originalSvg`` for
                 vector-only sources (e.g. an SVG / DXF upload where
                 no raster equivalent exists). -->
            <div
              v-if="hasSource && (viewMode === 'source' || viewMode === 'split')"
              class="artwork-svg artwork-svg--source"
              :style="viewMode === 'split' ? { clipPath: splitSourceClip } : {}"
              data-test="modal-v2-preview-source"
            >
              <img
                v-if="props.sourceImageUrl"
                :src="props.sourceImageUrl"
                :alt="t('v2.modal.viewOriginal')"
                class="artwork-source-img"
                draggable="false"
              />
              <!-- eslint-disable-next-line vue/no-v-html -->
              <div
                v-else-if="props.originalSvg"
                class="artwork-source-svg"
                v-html="props.originalSvg"
              />
            </div>
          </div>
          <!-- Vertical split-handle. Drag it left/right to sweep the
               reveal across the artwork. Only rendered in split mode
               so the handle never floats in plot-only or source-only. -->
          <div
            v-if="viewMode === 'split'"
            class="split-handle"
            :style="{ left: `${splitPercent}%` }"
            data-test="modal-v2-split-handle"
            @pointerdown="onSplitGrab"
            @pointermove="onSplitMove"
            @pointerup="onSplitRelease"
            @pointercancel="onSplitRelease"
          >
            <span class="split-handle__grip" aria-hidden="true">⇆</span>
          </div>
        </div>

        <!-- Unbounded fallback when no sheet is picked yet. The
             ``modal-v2-preview-svg`` data-test mirrors the
             sheet-bounded equivalent above so callers don't have to
             branch on the layout when asserting presence. -->
        <div v-else class="preview-viewport">
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
      </div>

      <!-- Three-way mode toggle: Result / Original / Compare. The
           V1 modal exposed the same set; restoring it keeps the
           operator able to verify what the conversion did to the
           source pixels. -->
      <div
        v-if="canShowOriginal"
        class="mode-toggle"
        data-test="modal-v2-mode-toggle"
        @pointerdown.stop
        @wheel.stop
        @dblclick.stop
      >
        <button
          type="button"
          :class="{ active: viewMode === 'plot' }"
          :aria-pressed="viewMode === 'plot'"
          :title="t('v2.modal.viewPlot')"
          data-test="modal-v2-mode-plot"
          @click="setMode('plot')"
        >
          {{ t('v2.modal.viewPlot') }}
        </button>
        <button
          type="button"
          :class="{ active: viewMode === 'source' }"
          :aria-pressed="viewMode === 'source'"
          :title="t('v2.modal.viewOriginal')"
          data-test="modal-v2-mode-source"
          @click="setMode('source')"
        >
          {{ t('v2.modal.viewOriginal') }}
        </button>
        <button
          type="button"
          :class="{ active: viewMode === 'split' }"
          :aria-pressed="viewMode === 'split'"
          :disabled="!canCompareOriginal"
          :title="t('v2.modal.viewCompare')"
          data-test="modal-v2-mode-split"
          @click="setMode('split')"
        >
          {{ t('v2.modal.viewCompare') }}
        </button>
      </div>

      <div class="zoom" data-test="modal-v2-zoom" @pointerdown.stop @wheel.stop @dblclick.stop>
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
          <span class="preview-overlay__percent" data-test="modal-v2-preview-percent">
            {{ displayPercent }} %
          </span>
          <span v-if="streamActive && streamLabel" class="preview-overlay__layer">
            · {{ streamLabel }}
          </span>
        </span>
        <!-- Progress bar: estimated fill from the cost-estimator EMA
             (per algorithm × quality), advanced by the SSE stream's
             real per-layer percent when one is active. Always visible
             while a preview is computing. -->
        <div
          class="preview-overlay__bar"
          role="progressbar"
          :aria-valuenow="displayPercent"
          aria-valuemin="0"
          aria-valuemax="100"
          data-test="modal-v2-preview-progress"
        >
          <div class="preview-overlay__bar-fill" :style="{ width: `${displayPercent}%` }" />
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
/* Root: flex column so the pane can flex against the gesture-hint
   line and absorb whatever height the parent column hands down. */
.preview-pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.preview {
  position: relative;
  /* The clamp is only the preferred size (flex-basis). Inside the
     modal's fixed-height left column the pane shrinks (down to the
     min-height below) so the sheet picker and ink chips underneath
     stay visible without scrolling; on narrow viewports the column
     is auto-sized and the clamp applies as-is. */
  height: clamp(320px, 62vh, 720px);
  flex: 1 1 auto;
  min-height: 240px;
  /* Dark checkerboard: the white sheet (paper) pops against it, same
     contrast logic as the main plan view. */
  background: repeating-conic-gradient(#1e293b 0% 25%, #0f172a 0% 50%) 0 / 20px 20px;
  border: 1px solid #334155;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
/* Stage holds the centring + zoom/pan transform. The sheet sits in
   the middle, so applying transform here scales the whole sheet (and
   the artwork inside it) without breaking the absolute centring. */
.preview-stage {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  will-change: transform;
}
.preview-viewport {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
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
/* Artwork box: sits at top-left of the sheet, sized to the drawing's
   real mm dimensions as a percentage of the sheet. Anchored top-left
   so the operator can read the artwork's actual position on the
   paper (we don't recentre to make a small drawing look big). */
.artwork-box {
  position: absolute;
  top: 0;
  left: 0;
  overflow: visible;
}
.artwork-svg {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.15s ease;
}
.artwork-svg.is-stale {
  opacity: 0.45;
}
.artwork-svg.is-hidden {
  display: none;
}
.artwork-svg :deep(svg) {
  width: 100%;
  height: 100%;
  display: block;
}
.artwork-svg--source :deep(svg),
.artwork-svg--source :deep(img) {
  /* Source SVG / fallback original may have its own background; keep
     it readable against the sheet. */
  background: transparent;
}
/* Raw source image: ``object-fit: contain`` mirrors the SVG's
   intrinsic sizing so the image obeys the same artwork-box bounds.
   ``user-select: none`` blocks the browser's default image-drag
   gesture from competing with the split-handle pointer events. */
.artwork-source-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  user-select: none;
  -webkit-user-drag: none;
}
.artwork-source-svg {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.artwork-source-svg :deep(svg) {
  width: 100%;
  height: 100%;
  display: block;
}
/* Split-handle: vertical reveal slider that sweeps between source
   and plot in compare mode. Lives at the sheet level so it tracks
   the sheet's transform (zoom/pan affect it together with the
   artwork). */
/* Split handle: wider hit zone (12 px) than visible line (2 px) so
   the operator can grab it without surgical precision. The visible
   bar is rendered via the ``::before`` pseudo so the grip dot can
   sit on top without losing the hit zone. */
.split-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 14px;
  background: transparent;
  cursor: ew-resize;
  z-index: 2;
  touch-action: none;
  transform: translateX(-7px);
  display: flex;
  align-items: center;
  justify-content: center;
}
.split-handle::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 2px;
  transform: translateX(-1px);
  background: #059669;
  pointer-events: none;
}
.split-handle__grip {
  position: relative;
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  background: #059669;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
  font-weight: bold;
  pointer-events: none;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.35);
}
/* Mode toggle (Result / Source / Compare). Lives in the top-right
   corner of the pane so it doesn't collide with the existing zoom
   controls in the top-left or the gesture-hint at the bottom. */
.mode-toggle {
  position: absolute;
  top: 0.5rem;
  left: 0.5rem;
  display: inline-flex;
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid #334155;
  border-radius: 4px;
  overflow: hidden;
  z-index: 3;
}
.mode-toggle button {
  border: none;
  background: transparent;
  color: #cbd5e1;
  font-size: 0.75rem;
  padding: 0.25rem 0.55rem;
  cursor: pointer;
  font-weight: 500;
}
.mode-toggle button + button {
  border-left: 1px solid #334155;
}
.mode-toggle button.active {
  background: #059669;
  color: white;
}
.mode-toggle button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.mode-toggle button:hover:not(.active):not(:disabled) {
  background: #334155;
}
.mode-toggle button:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
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
  background: rgba(15, 23, 42, 0.88);
  font-size: 0.75rem;
  color: #cbd5e1;
}
.preview-overlay__label {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.preview-overlay__layer {
  color: #34d399;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.75rem;
}
.preview-overlay__percent {
  color: #94a3b8;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
}
.preview-overlay__bar {
  width: min(100%, 240px);
  height: 4px;
  background: #334155;
  border-radius: 999px;
  overflow: hidden;
}
.preview-overlay__bar-fill {
  height: 100%;
  background: #10b981;
  border-radius: 999px;
  transition: width 0.15s ease;
}
.preview-error {
  position: absolute;
  inset: auto 0.5rem 0.5rem;
  margin: 0;
  text-align: center;
  font-size: 0.75rem;
  color: #fca5a5;
  background: rgba(69, 10, 10, 0.9);
  border: 1px solid #b91c1c;
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
  border: 1px solid #334155;
  background: rgba(15, 23, 42, 0.85);
  color: #e2e8f0;
  border-radius: 4px;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.zoom button:hover {
  background: #334155;
}
.zoom button:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.zoom-reset {
  font-size: 0.625rem !important;
  font-variant-numeric: tabular-nums;
}
.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #334155;
  border-top-color: #10b981;
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
  position: relative;
  /* Width/height come from the script setup's ``sheetStyle`` computed
     which derives them from the ResizeObserver-tracked pane size so
     the rectangle stays at the operator's chosen aspect ratio. The
     ``.preview-stage`` flex parent handles centring. */
  border: 1px dashed #64748b;
  /* Solid white: this rectangle *is* the paper — the one surface that
     stays light in the dark editor so the plot reads like ink on a
     sheet. */
  background: white;
  border-radius: 2px;
  /* Pointer events ON so the split-handle inside the sheet can be
     grabbed; the artwork-box has its own ``pointer-events: none``
     when needed. */
  pointer-events: auto;
  z-index: 0;
}
.sheet-caption {
  position: absolute;
  top: 2px;
  left: 4px;
  font-size: 0.625rem;
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
  border: 1px solid #334155;
  background: rgba(15, 23, 42, 0.85);
  color: #e2e8f0;
  border-radius: 999px;
  font-size: 0.75rem;
  cursor: pointer;
  z-index: 2;
}
.view-toggle:hover {
  background: #334155;
}
.view-toggle.is-original {
  background: rgba(2, 44, 34, 0.6);
  border-color: #059669;
  color: #6ee7b7;
}
.view-toggle:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}

.gesture-hint {
  margin: 0.35rem 0 0;
  font-size: 0.6875rem;
  color: #64748b;
  text-align: center;
  font-style: italic;
}
</style>
