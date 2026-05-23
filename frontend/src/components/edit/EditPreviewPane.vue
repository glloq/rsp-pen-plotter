<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../../stores/job'
import { useEditState } from '../../composables/useEditState'

const { t } = useI18n()
const store = useJobStore()
const edit = useEditState()

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

const showLivePreview = computed(() => Boolean(edit?.previewSvg.value))
const showPlacementSvg = computed(
  () => !showLivePreview.value && Boolean(placementSvg.value),
)
const showThumbnail = computed(
  () =>
    !showLivePreview.value
    && !showPlacementSvg.value
    && edit?.kind.value === 'bitmap'
    && Boolean(edit?.previewUrl.value),
)
const showTextPreview = computed(
  () =>
    !showLivePreview.value
    && !showPlacementSvg.value
    && edit?.kind.value === 'typography'
    && Boolean(edit?.textPreview.value),
)
const showEmptyHint = computed(
  () =>
    !showLivePreview.value
    && !showPlacementSvg.value
    && !showThumbnail.value
    && !showTextPreview.value,
)

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
</script>

<template>
  <section class="flex h-full min-h-0 flex-col">
    <header class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-slate-700 bg-slate-900/60 px-3 py-2 text-xs">
      <div class="flex flex-wrap items-baseline gap-x-3">
        <span class="uppercase tracking-wide text-slate-400">{{ t('editPreview.title') }}</span>
        <span v-if="edit?.selectedFile.value" class="truncate font-mono text-slate-300">
          {{ edit.selectedFile.value.name }}
        </span>
      </div>
      <span class="text-slate-400">{{ statusLabel }}</span>
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
        <!-- Vectorised placement SVG: the post-upload state, updated by
             /rerender when layer algorithms change. -->
        <div
          v-if="showPlacementSvg"
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

    <!-- Palette swatches from the live /preview, when available. -->
    <footer
      v-if="edit && edit.previewPalette.value.length"
      class="flex flex-wrap items-center gap-1.5 border-t border-slate-700 bg-slate-900/60 px-3 py-1.5 text-[10px] text-slate-500"
    >
      <span class="uppercase tracking-wider">{{ t('editPreview.palette') }}</span>
      <span
        v-for="hex in edit.previewPalette.value"
        :key="hex"
        class="inline-block h-3 w-3 rounded border border-slate-600"
        :style="{ backgroundColor: hex }"
        :title="hex"
      />
    </footer>
  </section>
</template>
