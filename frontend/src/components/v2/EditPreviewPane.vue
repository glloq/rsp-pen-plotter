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

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEditorPreviewZoomPan } from '../../composables/useEditorPreviewZoomPan'
import { useEditorPreviewSplit } from '../../composables/useEditorPreviewSplit'
import { useEditorPreviewStream } from '../../composables/useEditorPreviewStream'
import { useEditorPreviewSheetGeometry } from '../../composables/useEditorPreviewSheetGeometry'
import { useEditorPreviewSvgEffects } from '../../composables/useEditorPreviewSvgEffects'
import PreviewLoadingOverlay from './PreviewLoadingOverlay.vue'
import PreviewToolbar from './PreviewToolbar.vue'
import SafeSvgHtml from './SafeSvgHtml.vue'
import type { SheetOutlineShape } from './sheetGeometry'

// Re-exported so existing callers can keep importing the shape from this
// component; the canonical definition now lives in ``./sheetGeometry`` so the
// geometry composable can reference it without a circular import.
export type { SheetOutlineShape }

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
  /** Specific failure reason (network / backend), appended after the
   *  generic message when present. Optional — null shows the generic
   *  text alone. */
  errorMessage?: string | null
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

// The SVG painted in the sheet-bounded artwork box's "plot" layer.
// Falls back to the original placement SVG when no adapted render is
// available — documents and vectors aren't bitmap-rerenderable, so
// ``plotSvg`` stays null for them and the artwork box would otherwise
// render blank inside the sheet (the "no preview" a DOCX showed). The
// converted placement SVG *is* the plot for those sources.
const plotLayerSvg = computed<string | null>(() => props.plotSvg ?? props.originalSvg ?? null)

// Zoom / pan gesture vocabulary (wheel zooms, drag pans, double-click
// recentres) — owned by ``useEditorPreviewZoomPan``. The view is
// intentionally *not* reset on prop changes so the operator can flip
// intent ↔ palette while zoomed into a detail.
const {
  zoom,
  panning,
  contentStyle,
  onWheel,
  onPanStart,
  onPanMove,
  onPanEnd,
  zoomIn,
  zoomOut,
  resetView,
} = useEditorPreviewZoomPan()

// =========================================================================
// Sheet + artwork geometry.
// The pane's pixel size (ResizeObserver), the dashed-sheet fit, and the
// artwork-fraction sizing all live in ``useEditorPreviewSheetGeometry`` so
// the fit/clamp maths is testable without mounting the pane. ``paneEl`` is the
// template ref the observer watches; ``artworkFraction`` must be available
// before the split wiring below consumes it.
const { paneEl, paneWidth, paneHeight, sheetStyle, artworkFraction, artworkStyle } =
  useEditorPreviewSheetGeometry({
    sheet: () => props.sheet,
    artworkWidthMm: () => props.artworkWidthMm,
    artworkHeightMm: () => props.artworkHeightMm,
  })

// =========================================================================
// Split / compare slider.
// V1 had a vertical reveal: dragging the handle swept between the
// source preview (left half) and the converted result (right half).
// V2 inherits the same mechanic so the operator can verify what the
// algorithm did to the photo without leaving the modal.
// Compare (split) slider — the draggable reveal handle + its clip-paths.
// Owned by ``useEditorPreviewSplit`` (sheet-space pointer → artwork-space
// clip conversion lives there); resets to 50/50 on entering split mode.
const { splitPercent, onSplitGrab, onSplitMove, onSplitRelease, splitPlotClip, splitSourceClip } =
  useEditorPreviewSplit({ viewMode, artworkFraction })

// =========================================================================
// Progressive preview stream + estimated progress.
// ``useEditorPreviewStream`` owns the /preview/stream SSE open/close
// lifecycle (skipping sub-350 ms previews) and folds the real stream percent
// together with the estimated bar into a single ``displayPercent`` the
// loading overlay binds to. Self-cleaning on scope dispose.
const { streamLabel, streamActive, displayPercent } = useEditorPreviewStream({
  loading: () => props.loading,
  streamFileId: () => props.streamFileId,
  estimateMs: () => props.estimateMs,
})

// =========================================================================
// Preview-only SVG effects.
// The per-layer opacity overlay (ink-chip eye toggle + opacity slider) and
// the display-time stroke floor both walk the v-html'd SVG client-side.
// ``previewRoot`` is the shared render-surface ref (artwork box in sheet mode,
// unbounded viewport otherwise) and stays declared here so both template
// branches can bind it; the walks live in ``useEditorPreviewSvgEffects``.
const previewRoot = ref<HTMLElement | null>(null)
useEditorPreviewSvgEffects({
  previewRoot,
  viewMode,
  plotSvg: () => props.plotSvg,
  originalSvg: () => props.originalSvg,
  zoom,
  paneWidth,
  paneHeight,
  artworkStyle,
})
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
                 side. Injection goes through SafeSvgHtml (DOMPurify). -->
            <SafeSvgHtml
              v-if="plotLayerSvg"
              :svg="plotLayerSvg"
              class="artwork-svg artwork-svg--plot"
              :class="{ 'is-stale': loading, 'is-hidden': viewMode === 'source' }"
              :style="viewMode === 'split' ? { clipPath: splitPlotClip } : {}"
              data-test="modal-v2-preview-svg"
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
              <SafeSvgHtml
                v-else-if="props.originalSvg"
                :svg="props.originalSvg"
                class="artwork-source-svg"
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
          <div
            v-if="displayedSvg"
            ref="previewRoot"
            class="preview-svg"
            :class="{ 'is-stale': loading }"
            data-test="modal-v2-preview-svg"
          >
            <SafeSvgHtml :svg="displayedSvg" />
          </div>
        </div>
      </div>

      <!-- Floating controls: Result / Original / Compare toggle + zoom. -->
      <PreviewToolbar
        :view-mode="viewMode"
        :can-show-original="canShowOriginal"
        :can-compare-original="canCompareOriginal"
        :zoom="zoom"
        @set-mode="setMode"
        @zoom-in="zoomIn"
        @zoom-out="zoomOut"
        @reset-view="resetView"
      />

      <PreviewLoadingOverlay
        v-if="loading"
        :percent="displayPercent"
        :stream-active="streamActive"
        :stream-label="streamLabel"
      />
      <p v-if="error" class="preview-error" data-test="modal-v2-preview-error">
        {{ t('v2.modal.previewError')
        }}<span v-if="errorMessage" class="preview-error__detail"> — {{ errorMessage }}</span>
      </p>
    </div>
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
/* The Result/Original/Compare toggle + zoom cluster live in
   PreviewToolbar.vue; the loading spinner + progress bar live in
   PreviewLoadingOverlay.vue. Both position themselves against this
   pane's ``.preview`` container. */
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
.preview-error__detail {
  opacity: 0.85;
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

</style>
