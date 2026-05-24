<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../../stores/job'
import { useEditState } from '../../composables/useEditState'
import { useBitmapDraft } from '../../composables/useBitmapDraft'
import { usePreviewCostEstimator } from '../../composables/usePreviewCostEstimator'
import {
  getAlgorithms,
  type AlgorithmComplexity,
  type AlgorithmInfo,
} from '../../api/client'

const { t } = useI18n()
const store = useJobStore()
const edit = useEditState()
const draft = useBitmapDraft()
const costEstimator = usePreviewCostEstimator()

// Algorithm metadata cache. Fetched once on mount; the result feeds
// the cost chip's complexity seed. We tolerate the fetch failing —
// the estimator falls back to ``medium`` when the complexity is
// undefined, so the chip still renders.
const algorithmsInfo = ref<AlgorithmInfo[]>([])
onMounted(async () => {
  try { algorithmsInfo.value = await getAlgorithms() } catch { /* offline / 404 — fall through */ }
})
const currentComplexity = computed<AlgorithmComplexity>(() => {
  const algo = algorithmsInfo.value.find((a) => a.name === draft.bitmap.value.algorithm)
  return algo?.complexity ?? 'medium'
})
const estimatedMs = computed<number>(() =>
  costEstimator.estimateMs(
    draft.bitmap.value.algorithm,
    edit.previewQuality.value,
    currentComplexity.value,
  ),
)
// Format ms → human label. Sub-second renders show "120 ms"; otherwise
// switch to "1.4 s" so the operator parses it at a glance.
const estimatedLabel = computed<string>(() => {
  const ms = estimatedMs.value
  if (!Number.isFinite(ms) || ms <= 0) return ''
  if (ms < 1000) return `~${Math.round(ms)} ms`
  return `~${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`
})
// Tint the chip by predicted latency so a "this will hurt" estimate
// reads at a glance. Thresholds mirror the operator's rough patience
// budget on a Pi: under 300 ms feels instant, 300-1500 ms is the
// "slider drag wait" zone, beyond 1500 ms is "go grab a coffee".
const estimateTone = computed<'fast' | 'medium' | 'slow'>(() => {
  const ms = estimatedMs.value
  if (ms < 300) return 'fast'
  if (ms < 1500) return 'medium'
  return 'slow'
})
const estimateChipClass = computed<string>(() => {
  switch (estimateTone.value) {
    case 'fast':
      return 'border-emerald-700 bg-emerald-950/40 text-emerald-300'
    case 'medium':
      return 'border-amber-700 bg-amber-950/40 text-amber-300'
    case 'slow':
      return 'border-rose-700 bg-rose-950/40 text-rose-300'
  }
  return ''
})

// ============================== ZOOM & PAN ==============================
// Wheel zooms around the cursor (so the user can dig into a detail);
// drag pans. Both reset when the displayed source changes so the user
// doesn't reopen the modal and find the previous file half-off-screen.
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const panning = ref(false)
let panStartX = 0
let panStartY = 0
let panInitX = 0
let panInitY = 0
const MIN_ZOOM = 0.1
const MAX_ZOOM = 20

const contentStyle = computed(() => ({
  transform: `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`,
  transformOrigin: 'center center',
  transition: panning.value ? 'none' : 'transform 0.08s ease-out',
}))

function clampZoom(value: number): number {
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, value))
}

function isTransformable(): boolean {
  // Text-only previews keep their own scroll behaviour and the empty
  // hint has nothing to zoom; both opt out of pan/zoom.
  return !showTextPreview.value && !showEmptyHint.value
}

function onWheel(event: WheelEvent): void {
  if (!isTransformable()) return
  event.preventDefault()
  const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15
  zoom.value = clampZoom(zoom.value * factor)
}

function onPanStart(event: PointerEvent): void {
  if (!isTransformable()) return
  // Left-click and middle-click both pan; right-click stays for the
  // browser context menu in case the user wants to inspect.
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

function resetView(): void {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
}

function zoomIn(): void {
  zoom.value = clampZoom(zoom.value * 1.25)
}

function zoomOut(): void {
  zoom.value = clampZoom(zoom.value / 1.25)
}

// Reset zoom/pan when the source content changes so a new file always
// lands fit-to-view.
watch(
  [() => edit.selectedFile.value, () => edit.currentPage.value],
  resetView,
)

// Variant chips in the toolbar mirror the right-pane VariantsCard for
// quick switching while keeping eyes on the preview.
const variants = computed(() => store.selectedPlacement?.variants ?? [])
const activeVariantId = computed(() => store.selectedPlacement?.active_variant_id ?? '')

// Render order:
//   1. If /preview returned an SVG for the current draft settings,
//      show that — it reflects the user's in-flight edits. The
//      previewResult is cleared after a successful upload so this
//      only wins while the user is drafting.
//   2. Else if a placement is already committed (job_id + svg present),
//      show its vectorised SVG — updated by /rerender on layer algo
//      changes.
//   3. Else fall back to the local raster thumbnail (bitmap) or the
//      text sample (typography).
const placementSvg = computed(() => {
  const svg = store.svg
  if (!svg) return ''
  return DOMPurify.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true } })
})

// ``source`` mode (set by EditModal when the Image tab is active)
// forces the raster source + preprocess overlay even when an SVG
// preview is ready, so the operator can see what their brightness /
// contrast / crop tweaks are doing to the *source pixels*. ``split``
// shows both halves so the operator can compare CSS-only preprocess
// (left) against the full vectorisation (right) — critical for
// gamma / levels / sharpen which CSS can't express. ``auto`` falls
// back to the regular SVG flow on every other tab.
const sourceMode = computed(
  () =>
    edit.previewMode.value === 'source'
    && edit.kind.value === 'bitmap'
    && Boolean(edit.previewUrl.value),
)
// Split mode requires both halves to have content; if either is
// missing we degrade to whichever single layer is available rather
// than showing an awkward half-empty pane.
const hasLiveSvg = computed(() => Boolean(edit?.previewSvg.value))
const hasRaster = computed(
  () => edit.kind.value === 'bitmap' && Boolean(edit.previewUrl.value),
)
const splitMode = computed(
  () =>
    edit.previewMode.value === 'split'
    && hasRaster.value
    && (hasLiveSvg.value || Boolean(placementSvg.value)),
)
const showLivePreview = computed(
  () => !sourceMode.value && !splitMode.value && hasLiveSvg.value,
)
const showPlacementSvg = computed(
  () =>
    !sourceMode.value
    && !splitMode.value
    && !showLivePreview.value
    && Boolean(placementSvg.value),
)
const showSourcePreview = computed(() => sourceMode.value)
const showSplitPreview = computed(() => splitMode.value)
const showThumbnail = computed(
  () =>
    !sourceMode.value
    && !splitMode.value
    && !showLivePreview.value
    && !showPlacementSvg.value
    && edit?.kind.value === 'bitmap'
    && Boolean(edit?.previewUrl.value),
)
const showTextPreview = computed(
  () =>
    !sourceMode.value
    && !splitMode.value
    && !showLivePreview.value
    && !showPlacementSvg.value
    && edit?.kind.value === 'typography'
    && Boolean(edit?.textPreview.value),
)
const showEmptyHint = computed(
  () =>
    !sourceMode.value
    && !splitMode.value
    && !showLivePreview.value
    && !showPlacementSvg.value
    && !showThumbnail.value
    && !showTextPreview.value,
)

// Which SVG should the right half of the split show? Prefer the live
// /preview (reflects unsaved edits) over the committed placement SVG.
const splitSvg = computed<string>(() =>
  edit.previewSvg.value || placementSvg.value,
)

// Toolbar visibility: only meaningful when the source is a bitmap and
// both raster + a vector representation could potentially be shown.
const canToggleMode = computed(
  () => edit.kind.value === 'bitmap' && hasRaster.value,
)
const QUALITY_TIERS: Array<{ id: 'draft' | 'standard' | 'final'; key: string }> = [
  { id: 'draft', key: 'editPreview.qualityDraft' },
  { id: 'standard', key: 'editPreview.qualityStandard' },
  { id: 'final', key: 'editPreview.qualityFinal' },
]
const MODE_TOGGLES: Array<{ id: 'auto' | 'source' | 'split'; key: string }> = [
  { id: 'auto', key: 'editPreview.modeAuto' },
  { id: 'source', key: 'editPreview.modeSource' },
  { id: 'split', key: 'editPreview.modeSplit' },
]

// CSS filter / transform / clip-path that mirror the operator's
// PreprocessDraft so the raw source preview reflects their tweaks live
// without a server round-trip. Caveats noted in the i18n hint:
// gamma, levels, sharpen and auto-contrast aren't expressible in
// stock CSS — those land in the SVG preview once the operator
// switches tabs. The colour adjustments (brightness, contrast,
// saturation, blur, invert, grayscale) and the geometric ones
// (rotate, flip, crop) are exact.
const sourceImageStyle = computed<Record<string, string>>(() => {
  const p = draft.bitmap.value.preprocess
  const filters: string[] = []
  if (p.brightness !== 0) filters.push(`brightness(${1 + p.brightness})`)
  if (p.contrast !== 0) filters.push(`contrast(${1 + p.contrast})`)
  if (p.saturation !== 1) filters.push(`saturate(${p.saturation})`)
  if (p.blur_px > 0) filters.push(`blur(${p.blur_px}px)`)
  if (p.invert) filters.push('invert(1)')
  if (p.grayscale) filters.push('grayscale(1)')
  const transforms: string[] = []
  if (p.rotate_deg) transforms.push(`rotate(${p.rotate_deg}deg)`)
  const sx = p.flip_h ? -1 : 1
  const sy = p.flip_v ? -1 : 1
  if (sx !== 1 || sy !== 1) transforms.push(`scale(${sx}, ${sy})`)
  const style: Record<string, string> = {
    maxHeight: '100%',
    maxWidth: '100%',
    objectFit: 'contain',
  }
  if (filters.length) style.filter = filters.join(' ')
  if (transforms.length) style.transform = transforms.join(' ')
  if (p.crop) {
    const [x, y, w, h] = p.crop
    const top = (y * 100).toFixed(2)
    const right = ((1 - (x + w)) * 100).toFixed(2)
    const bottom = ((1 - (y + h)) * 100).toFixed(2)
    const left = (x * 100).toFixed(2)
    style.clipPath = `inset(${top}% ${right}% ${bottom}% ${left}%)`
  }
  return style
})

// Crop overlay rectangle: rendered above the raster to make the
// kept region obvious (dark mask outside, clear inside). Only emitted
// when the operator actually enabled a crop.
const cropOverlay = computed<{ x: string; y: string; w: string; h: string } | null>(() => {
  const p = draft.bitmap.value.preprocess
  if (!p.crop) return null
  const [x, y, w, h] = p.crop
  return {
    x: `${(x * 100).toFixed(2)}%`,
    y: `${(y * 100).toFixed(2)}%`,
    w: `${(w * 100).toFixed(2)}%`,
    h: `${(h * 100).toFixed(2)}%`,
  }
})

const statusLabel = computed(() => {
  if (!edit) return ''
  if (edit.previewLoading.value) return t('upload.previewing')
  if (edit.previewError.value) return edit.previewError.value
  if (edit.previewElapsedMs.value !== null) {
    const cached = edit.previewCached.value ? ` · ${t('upload.cached')}` : ''
    return `${edit.previewElapsedMs.value} ms${cached}`
  }
  return ''
})

// SVG diagnostics — concrete proof that the detail / mode tweaks
// actually change the rendered output. Without this, the live preview
// auto-scales to fit the pane so a 400×400 result and a 1200×1200
// result look visually similar even though one has 4× the paths. The
// footer reports the SVG's viewBox size and a path-element count so
// the operator can verify "yes, switching to High really did rebuild
// the SVG at higher resolution".
const currentSvg = computed<string>(() => {
  if (edit?.previewSvg.value) return edit.previewSvg.value
  return placementSvg.value
})

const svgStats = computed<{ width: number; height: number; paths: number } | null>(() => {
  const svg = currentSvg.value
  if (!svg) return null
  const vbMatch = svg.match(/viewBox="([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)"/)
  const width = vbMatch ? Math.round(Number(vbMatch[3])) : 0
  const height = vbMatch ? Math.round(Number(vbMatch[4])) : 0
  // Count the renderer's primitive elements: <path>, <line>, <circle>,
  // <polyline>, <polygon>. Each is roughly one pen stroke.
  const paths
    = (svg.match(/<path /g)?.length ?? 0)
    + (svg.match(/<line /g)?.length ?? 0)
    + (svg.match(/<circle /g)?.length ?? 0)
    + (svg.match(/<polyline /g)?.length ?? 0)
    + (svg.match(/<polygon /g)?.length ?? 0)
  if (!width && !height && !paths) return null
  return { width, height, paths }
})
</script>

<template>
  <section class="flex h-full min-h-0 flex-col">
    <header class="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-slate-700 bg-slate-900/60 px-3 py-2 text-xs">
      <div class="flex flex-wrap items-center gap-x-2">
        <span class="uppercase tracking-wide text-slate-400">{{ t('editPreview.title') }}</span>
        <!-- View mode toggle: Auto (default flow), Source (raster +
             CSS preprocess), Split (raster | vector compare). Hidden
             when there's no raster to compare with — typography /
             empty panes have nothing to toggle. -->
        <div
          v-if="canToggleMode"
          class="flex items-center gap-px rounded-sm border border-slate-700 bg-slate-950/40 p-px"
          role="group"
          :aria-label="t('editPreview.modeGroup')"
        >
          <button
            v-for="m in MODE_TOGGLES"
            :key="m.id"
            type="button"
            class="rounded-sm px-1.5 py-0.5 text-[10px] uppercase tracking-wider transition"
            :class="edit.previewMode.value === m.id
              ? 'bg-sky-800/70 text-sky-100'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'"
            :title="t(`${m.key}Hint`)"
            @click="edit.previewMode.value = m.id"
          >
            {{ t(m.key) }}
          </button>
        </div>
        <!-- Quality tier: Draft for slider-drag latency, Standard
             matches the historical /preview behaviour, Final pays for
             10-restart k-means. Each tier has its own cache slot so
             toggling between them stays cheap after the first warm-up. -->
        <div
          class="flex items-center gap-px rounded-sm border border-slate-700 bg-slate-950/40 p-px"
          role="group"
          :aria-label="t('editPreview.qualityGroup')"
        >
          <button
            v-for="q in QUALITY_TIERS"
            :key="q.id"
            type="button"
            class="rounded-sm px-1.5 py-0.5 text-[10px] uppercase tracking-wider transition"
            :class="edit.previewQuality.value === q.id
              ? 'bg-emerald-800/70 text-emerald-100'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'"
            :title="t(`${q.key}Hint`)"
            @click="edit.previewQuality.value = q.id"
          >
            {{ t(q.key) }}
          </button>
        </div>
        <!-- LIVE vs SAVED badge: tells the operator at a glance whether
             the canvas is showing the freshly-rendered draft (every
             setting change updates it) or the last committed
             placement SVG (only Re-convert refreshes it). Without
             this, settings changes that updated the live preview but
             not the placement looked like "nothing happened". -->
        <span
          v-if="showSplitPreview"
          class="rounded-sm border border-violet-700 bg-violet-950/60 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider text-violet-300"
          :title="t('editPreview.splitHint')"
        >{{ t('editPreview.split') }}</span>
        <span
          v-else-if="showSourcePreview"
          class="rounded-sm border border-sky-700 bg-sky-950/60 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider text-sky-300"
          :title="t('editPreview.sourceHint')"
        >{{ t('editPreview.source') }}</span>
        <span
          v-else-if="showLivePreview"
          class="rounded-sm border border-emerald-700 bg-emerald-950/60 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider text-emerald-300"
          :title="t('editPreview.livePreviewHint')"
        >{{ t('editPreview.live') }}</span>
        <span
          v-else-if="showPlacementSvg"
          class="rounded-sm border border-slate-700 bg-slate-900/60 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wider text-slate-400"
          :title="t('editPreview.savedHint')"
        >{{ t('editPreview.saved') }}</span>
        <span v-if="edit?.selectedFile.value" class="truncate font-mono text-slate-300">
          {{ edit.selectedFile.value.name }}
        </span>
      </div>
      <div class="flex items-center gap-2">
        <!-- Cost estimate chip. Reads the per-(algorithm, quality) EMA
             fed by the preview scheduler, seeded by the algorithm's
             static complexity from /algorithms. Tinted by tone so an
             impending multi-second render is obvious at a glance —
             the operator can downgrade Final → Standard before
             committing. -->
        <span
          v-if="estimatedLabel && edit.kind.value === 'bitmap'"
          class="rounded-sm border px-1.5 py-px font-mono text-[10px]"
          :class="estimateChipClass"
          :title="t('editPreview.estimateHint', { complexity: t(`editPreview.complexity_${currentComplexity}`) })"
        >{{ estimatedLabel }}</span>
        <span class="text-slate-400">{{ statusLabel }}</span>
      </div>
    </header>

    <!-- Variant chips: quick switch + reflect the active variant
         currently shown by the preview. -->
    <nav
      v-if="variants.length > 1"
      class="flex flex-wrap items-center gap-1 border-b border-slate-700 bg-slate-900/40 px-3 py-1.5 text-[11px]"
    >
      <span class="uppercase tracking-wider text-slate-500">{{ t('variants.title') }}</span>
      <button
        v-for="variant in variants"
        :key="variant.id"
        type="button"
        class="rounded border px-2 py-0.5 text-[11px] transition"
        :class="variant.id === activeVariantId
          ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
          : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'"
        @click="store.setActiveVariant(variant.id)"
      >
        {{ variant.name }}
      </button>
    </nav>

    <!-- Page selector for PDFs and other multi-page documents. -->
    <nav
      v-if="edit && edit.pageCount.value > 1"
      class="flex items-center justify-between border-b border-slate-700 bg-slate-900/40 px-3 py-1 text-xs"
    >
      <button
        type="button"
        class="rounded bg-slate-800 px-2 py-0.5 text-slate-200 hover:bg-slate-700 disabled:opacity-40"
        :disabled="edit.currentPage.value <= 0"
        :aria-label="t('upload.prevPage')"
        @click="edit.goToPage(edit.currentPage.value - 1)"
      >
        ←
      </button>
      <span class="text-slate-300">
        {{ t('upload.pageOf', { current: edit.currentPage.value + 1, total: edit.pageCount.value }) }}
      </span>
      <button
        type="button"
        class="rounded bg-slate-800 px-2 py-0.5 text-slate-200 hover:bg-slate-700 disabled:opacity-40"
        :disabled="edit.currentPage.value >= edit.pageCount.value - 1"
        :aria-label="t('upload.nextPage')"
        @click="edit.goToPage(edit.currentPage.value + 1)"
      >
        →
      </button>
    </nav>

    <!-- Pannable / zoomable preview canvas. The wrapper captures pointer
         events; the inner div applies the transform so the content
         scales / translates as one. Text previews and the empty hint
         opt out at the handler level — see isTransformable(). -->
    <div
      class="relative min-h-0 flex-1 overflow-hidden bg-white"
      :style="{
        cursor: showTextPreview || showEmptyHint
          ? 'default'
          : panning ? 'grabbing' : 'grab',
        touchAction: 'none',
      }"
      @wheel="onWheel"
      @pointerdown="onPanStart"
      @pointermove="onPanMove"
      @pointerup="onPanEnd"
      @pointercancel="onPanEnd"
      @dblclick="resetView"
    >
      <div
        class="absolute inset-0 flex items-center justify-center p-3"
        :style="contentStyle"
      >
        <!-- Source-pixel preview: the raw raster with the operator's
             preprocess adjustments overlaid via CSS filters /
             transforms / clip-path. Active on the Image tab so the
             operator sees what their tweaks do to the *source*
             before segmentation runs. The crop region is also
             outlined with a dark mask so the kept area is obvious. -->
        <div
          v-if="showSourcePreview"
          class="relative flex h-full w-full items-center justify-center"
        >
          <img
            :src="edit!.previewUrl.value!"
            :alt="edit!.selectedFile.value?.name ?? ''"
            class="block"
            :style="sourceImageStyle"
            draggable="false"
          />
          <!-- Crop guide: a 4-quadrant dark mask makes the kept region
               unmistakable while the operator dials in the crop. -->
          <template v-if="cropOverlay">
            <div class="pointer-events-none absolute inset-0">
              <div class="absolute inset-x-0 top-0 bg-black/55" :style="{ height: cropOverlay.y }" />
              <div
                class="absolute inset-x-0 bottom-0 bg-black/55"
                :style="{
                  top: `calc(${cropOverlay.y} + ${cropOverlay.h})`,
                }"
              />
              <div
                class="absolute bg-black/55"
                :style="{
                  top: cropOverlay.y,
                  left: 0,
                  width: cropOverlay.x,
                  height: cropOverlay.h,
                }"
              />
              <div
                class="absolute bg-black/55"
                :style="{
                  top: cropOverlay.y,
                  left: `calc(${cropOverlay.x} + ${cropOverlay.w})`,
                  right: 0,
                  height: cropOverlay.h,
                }"
              />
              <div
                class="absolute border-2 border-emerald-400/80"
                :style="{
                  top: cropOverlay.y,
                  left: cropOverlay.x,
                  width: cropOverlay.w,
                  height: cropOverlay.h,
                }"
              />
            </div>
          </template>
        </div>
        <!-- Split-screen compare: raster (left, with CSS preprocess
             overlay) vs vectorisation (right). The divider sits at
             50% with a thin labelled separator so the operator can
             eyeball gamma / levels / sharpen — adjustments that CSS
             can't express but that the backend pipeline applies in
             full. Each half clip-paths the same content the single-
             mode renderers use, so there's no duplicated style logic. -->
        <div
          v-else-if="showSplitPreview"
          class="relative flex h-full w-full items-center justify-center"
        >
          <!-- Left half: source raster + CSS preprocess overlay. -->
          <div
            class="absolute inset-0 flex items-center justify-center overflow-hidden"
            :style="{ clipPath: 'inset(0 50% 0 0)' }"
          >
            <img
              :src="edit!.previewUrl.value!"
              :alt="edit!.selectedFile.value?.name ?? ''"
              class="block"
              :style="sourceImageStyle"
              draggable="false"
            />
            <template v-if="cropOverlay">
              <div class="pointer-events-none absolute inset-0">
                <div class="absolute inset-x-0 top-0 bg-black/55" :style="{ height: cropOverlay.y }" />
                <div
                  class="absolute inset-x-0 bottom-0 bg-black/55"
                  :style="{ top: `calc(${cropOverlay.y} + ${cropOverlay.h})` }"
                />
                <div
                  class="absolute bg-black/55"
                  :style="{ top: cropOverlay.y, left: 0, width: cropOverlay.x, height: cropOverlay.h }"
                />
                <div
                  class="absolute bg-black/55"
                  :style="{
                    top: cropOverlay.y,
                    left: `calc(${cropOverlay.x} + ${cropOverlay.w})`,
                    right: 0,
                    height: cropOverlay.h,
                  }"
                />
                <div
                  class="absolute border-2 border-emerald-400/80"
                  :style="{
                    top: cropOverlay.y,
                    left: cropOverlay.x,
                    width: cropOverlay.w,
                    height: cropOverlay.h,
                  }"
                />
              </div>
            </template>
          </div>
          <!-- Right half: full vectorisation. v-html is sanitised
               upstream (placementSvg + previewSvg both run through
               DOMPurify). -->
          <div
            class="absolute inset-0 flex items-center justify-center overflow-hidden [&_svg]:max-h-full [&_svg]:max-w-full"
            :style="{ clipPath: 'inset(0 0 0 50%)' }"
            v-html="splitSvg"
          />
          <!-- Divider + labels. The divider is non-interactive (no
               drag handle in v1 — we revisit if operators ask). The
               labels float above the canvas so they survive the
               clip-paths. -->
          <div class="pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-slate-400/70" />
          <span
            class="pointer-events-none absolute left-2 top-2 rounded-sm bg-slate-900/80 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-slate-200"
          >{{ t('editPreview.source') }}</span>
          <span
            class="pointer-events-none absolute right-2 top-2 rounded-sm bg-slate-900/80 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-slate-200"
          >{{ t('editPreview.vector') }}</span>
        </div>
        <!-- Vectorised placement SVG: the post-upload state, updated by
             /rerender when layer algorithms change. -->
        <div
          v-else-if="showPlacementSvg"
          class="flex h-full w-full items-center justify-center [&_svg]:max-h-full [&_svg]:max-w-full"
          v-html="placementSvg"
        />
        <!-- Live /preview SVG: pre-upload state, fed by the draft
             settings on the right pane. -->
        <div
          v-else-if="showLivePreview"
          class="flex h-full w-full items-center justify-center [&_svg]:max-h-full [&_svg]:max-w-full"
          v-html="edit!.previewSvg.value"
        />
        <!-- Local raster thumbnail: lowest-cost fallback for images
             that haven't been uploaded or previewed yet. -->
        <img
          v-else-if="showThumbnail"
          :src="edit!.previewUrl.value!"
          :alt="edit!.selectedFile.value?.name ?? ''"
          class="max-h-full max-w-full object-contain"
          draggable="false"
        />
        <pre
          v-else-if="showTextPreview"
          class="m-0 max-h-full w-full overflow-auto whitespace-pre-wrap rounded border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700"
          >{{ edit!.textPreview.value }}</pre
        >
        <div
          v-else-if="showEmptyHint"
          class="flex flex-col items-center gap-2 text-center text-slate-400"
        >
          <span class="text-5xl text-slate-300" aria-hidden="true">🖼</span>
          <p class="text-sm">{{ t('editPreview.empty') }}</p>
          <p class="text-xs text-slate-500">{{ t('editPreview.emptyHint') }}</p>
        </div>
      </div>

      <!-- Floating zoom controls overlay the canvas; pointer-events on
           the buttons themselves opt out of the pan capture above. -->
      <div
        v-if="!showTextPreview && !showEmptyHint"
        class="absolute right-2 top-2 flex flex-col gap-1 rounded bg-slate-900/70 p-1 text-xs text-slate-200"
        @pointerdown.stop
        @wheel.stop
        @dblclick.stop
      >
        <button
          type="button"
          class="h-6 w-6 rounded bg-slate-800 hover:bg-slate-700"
          :title="t('editPreview.zoomIn')"
          @click="zoomIn"
        >+</button>
        <button
          type="button"
          class="h-6 w-6 rounded bg-slate-800 hover:bg-slate-700"
          :title="t('editPreview.zoomOut')"
          @click="zoomOut"
        >−</button>
        <button
          type="button"
          class="h-6 w-6 rounded bg-slate-800 text-[10px] hover:bg-slate-700"
          :title="t('editPreview.resetView')"
          @click="resetView"
        >{{ Math.round(zoom * 100) }}</button>
      </div>

      <!-- Loading bar + cancel button overlay. The animated bar at the
           top is purely cosmetic; the centred badge lets the operator
           bail on a long-running /preview call instead of waiting. -->
      <div
        v-if="edit?.previewLoading.value"
        class="pointer-events-none absolute inset-x-0 top-0 h-0.5 animate-pulse bg-emerald-400"
      />
      <button
        v-if="edit?.previewLoading.value"
        type="button"
        class="absolute left-1/2 top-3 -translate-x-1/2 rounded-full bg-slate-900/90 px-3 py-1 text-[11px] text-slate-100 shadow-lg hover:bg-slate-800"
        :title="t('editPreview.cancelPreview')"
        @click="edit?.cancelPreview()"
      >
        ⏸ {{ t('editPreview.cancelPreview') }}
      </button>

      <!-- Failed preview: surface error + one-click retry instead of
           leaving the operator wondering why the canvas is stale. -->
      <div
        v-if="edit?.previewError.value && !edit?.previewLoading.value"
        class="absolute left-1/2 top-3 -translate-x-1/2 flex max-w-md items-center gap-2 rounded-md border border-red-700 bg-red-950/90 px-3 py-1.5 text-[11px] text-red-200 shadow-lg"
      >
        <span class="truncate">{{ edit?.previewError.value }}</span>
        <button
          type="button"
          class="shrink-0 rounded bg-red-900 px-2 py-0.5 text-[10px] text-red-100 hover:bg-red-800"
          @click="edit?.retryPreview()"
        >
          ↻ {{ t('editPreview.retry') }}
        </button>
      </div>
    </div>

    <!-- Status footer: SVG diagnostics (dimensions + path count) plus
         the live palette swatches when /preview returned a palette.
         The diagnostics make detail / mode tweaks visible — the
         preview pane scales the SVG to fit, so a higher-detail SVG
         looks the same as a lower-detail one at first glance even
         though the path count multiplied. -->
    <footer
      v-if="svgStats || (edit && edit.previewPalette.value.length)"
      class="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-slate-700 bg-slate-900/60 px-3 py-1.5 text-[10px] text-slate-500"
    >
      <span v-if="svgStats" class="font-mono text-slate-400">
        {{ svgStats.width }} × {{ svgStats.height }}
        · {{ svgStats.paths }} {{ t('editPreview.paths') }}
      </span>
      <template v-if="edit && edit.previewPalette.value.length">
        <span class="uppercase tracking-wider">{{ t('editPreview.palette') }}</span>
        <span
          v-for="hex in edit.previewPalette.value"
          :key="hex"
          class="inline-block h-3 w-3 rounded border border-slate-600"
          :style="{ backgroundColor: hex }"
          :title="hex"
        />
      </template>
    </footer>
  </section>
</template>
