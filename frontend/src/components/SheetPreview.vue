<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import DOMPurify from 'dompurify'
import { useJobStore } from '../stores/job'
import { computePlacement, unionBounds } from '../lib/placement'

const { t } = useI18n()
const store = useJobStore()

const data = computed(() => {
  const profile = store.selectedProfile
  if (!profile || store.layers.length === 0) return null
  const bounds = unionBounds(store.layers.map((l) => l.bbox))
  if (!bounds) return null
  const ws = profile.workspace
  const wsW = ws.x_max - ws.x_min
  const wsH = ws.y_max - ws.y_min
  if (wsW <= 0 || wsH <= 0) return null
  // The sheet is the actual paper; the drawing is centred inside the sheet,
  // not the workspace. Default sheet = full workspace (a fresh profile).
  const sheet = store.currentSheet ?? {
    width: wsW,
    height: wsH,
    offsetX: 0,
    offsetY: 0,
  }
  const sheetRect = {
    x_min: ws.x_min + sheet.offsetX,
    y_min: ws.y_min + sheet.offsetY,
    x_max: ws.x_min + sheet.offsetX + sheet.width,
    y_max: ws.y_min + sheet.offsetY + sheet.height,
  }
  const placement = computePlacement(
    bounds,
    profile,
    store.scaleMode,
    store.marginMm,
    sheetRect,
  )
  const pad = Math.max(wsW, wsH) * 0.04
  const sheetExceedsWorkspace
    = sheet.offsetX < -0.01
    || sheet.offsetY < -0.01
    || sheet.offsetX + sheet.width > wsW + 0.01
    || sheet.offsetY + sheet.height > wsH + 0.01
  return { profile, placement, ws, wsW, wsH, pad, sheet, sheetRect, sheetExceedsWorkspace }
})

const scaleLabel = computed(() => {
  if (!data.value) return ''
  if (store.scaleMode === 'actual') return '1:1'
  return `${(data.value.placement.scale * 100).toFixed(0)}%`
})

// View transform — independent from the drawing scale; this is just how the
// user is looking at the sheet (zoom/pan inside the preview pane).
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const isDragging = ref(false)
let lastX = 0
let lastY = 0

function resetView(): void {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
}

// New job or new profile → reset the view so the user isn't stuck zoomed in
// on whatever they were looking at before.
watch(
  () => store.job?.job_id,
  () => resetView(),
)
watch(
  () => store.selectedProfileName,
  () => resetView(),
)

function onWheel(event: WheelEvent): void {
  event.preventDefault()
  const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15
  const next = Math.max(0.2, Math.min(zoom.value * factor, 12))
  zoom.value = next
}

function onPointerDown(event: PointerEvent): void {
  if (event.button !== 0 && event.button !== 1) return
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  isDragging.value = true
  lastX = event.clientX
  lastY = event.clientY
}

function onPointerMove(event: PointerEvent): void {
  if (!isDragging.value) return
  panX.value += event.clientX - lastX
  panY.value += event.clientY - lastY
  lastX = event.clientX
  lastY = event.clientY
}

function onPointerUp(event: PointerEvent): void {
  if (!isDragging.value) return
  isDragging.value = false
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
}

// Optional in-sheet rendering of the actual drawing for a better visual
// reference. We embed the sanitized job SVG inside a <foreignObject>
// positioned to match the placement footprint.
const cleanSvg = computed(() => {
  if (!store.svg) return ''
  return DOMPurify.sanitize(store.svg, { USE_PROFILES: { svg: true, svgFilters: true } })
})

const svgWrapper = ref<HTMLDivElement | null>(null)

onBeforeUnmount(() => {
  // No global listeners to clean up; pointer capture is auto-released.
})
</script>

<template>
  <div
    v-if="data"
    class="rounded-lg border border-slate-700 bg-slate-800/60 p-3"
  >
    <div class="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-xs">
      <h2 class="uppercase tracking-wide text-slate-400">{{ t('sheet.title') }}</h2>
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-slate-300">
        <span>{{ t('sheet.workArea') }}: {{ data.wsW.toFixed(0) }}×{{ data.wsH.toFixed(0) }} mm</span>
        <span>{{ t('sheet.sheet') }}: {{ data.sheet.width.toFixed(0) }}×{{ data.sheet.height.toFixed(0) }} mm</span>
        <span>
          {{ t('sheet.drawing') }}:
          {{ data.placement.widthMm.toFixed(0) }}×{{ data.placement.heightMm.toFixed(0) }} mm
        </span>
        <span>{{ t('sheet.scale') }}: {{ scaleLabel }}</span>
        <span class="text-slate-500">·</span>
        <span class="text-slate-400">{{ t('sheet.view') }}: {{ Math.round(zoom * 100) }}%</span>
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300 hover:bg-slate-800"
          @click="resetView"
        >
          {{ t('sheet.resetView') }}
        </button>
      </div>
    </div>

    <div
      class="relative w-full overflow-hidden rounded border border-slate-700 bg-slate-900/40 select-none"
      :style="{ aspectRatio: `${data.wsW + 2 * data.pad} / ${data.wsH + 2 * data.pad}`, maxHeight: '60vh', touchAction: 'none', cursor: isDragging ? 'grabbing' : 'grab' }"
      @wheel="onWheel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
    >
      <div
        ref="svgWrapper"
        class="absolute inset-0"
        :style="{ transform: `translate(${panX}px, ${panY}px) scale(${zoom})`, transformOrigin: '50% 50%' }"
      >
        <svg
          :viewBox="`${data.ws.x_min - data.pad} ${data.ws.y_min - data.pad} ${data.wsW + 2 * data.pad} ${data.wsH + 2 * data.pad}`"
          class="h-full w-full"
          role="img"
          :aria-label="t('sheet.title')"
        >
          <!-- Workspace = machine's physical drawable envelope. Greyed out so
               the user can see how much room they're leaving on the bed. -->
          <rect
            :x="data.ws.x_min"
            :y="data.ws.y_min"
            :width="data.wsW"
            :height="data.wsH"
            fill="#475569"
            fill-opacity="0.15"
            stroke="#64748b"
            stroke-width="1"
            stroke-dasharray="6 4"
            vector-effect="non-scaling-stroke"
          />
          <!-- Sheet = actual paper loaded. White, with a red outline if it
               exceeds the workspace (impossible to plot). -->
          <rect
            :x="data.sheetRect.x_min"
            :y="data.sheetRect.y_min"
            :width="Math.max(data.sheet.width, 0)"
            :height="Math.max(data.sheet.height, 0)"
            fill="#ffffff"
            :stroke="data.sheetExceedsWorkspace ? '#dc2626' : '#475569'"
            stroke-width="1"
            vector-effect="non-scaling-stroke"
          />
          <rect
            v-if="store.scaleMode === 'fit' && store.marginMm > 0"
            :x="data.sheetRect.x_min + store.marginMm"
            :y="data.sheetRect.y_min + store.marginMm"
            :width="Math.max(data.sheet.width - 2 * store.marginMm, 0)"
            :height="Math.max(data.sheet.height - 2 * store.marginMm, 0)"
            fill="none"
            stroke="#94a3b8"
            stroke-width="1"
            stroke-dasharray="4 3"
            vector-effect="non-scaling-stroke"
          />
          <!-- Embedded drawing preview: positioned to match the footprint
               the G-code generator will produce. -->
          <foreignObject
            v-if="cleanSvg"
            :x="data.placement.footprint.x_min"
            :y="data.placement.footprint.y_min"
            :width="Math.max(data.placement.footprint.x_max - data.placement.footprint.x_min, 0.01)"
            :height="Math.max(data.placement.footprint.y_max - data.placement.footprint.y_min, 0.01)"
          >
            <div
              xmlns="http://www.w3.org/1999/xhtml"
              class="h-full w-full overflow-hidden"
              v-html="cleanSvg"
            />
          </foreignObject>
          <rect
            :x="data.placement.footprint.x_min"
            :y="data.placement.footprint.y_min"
            :width="data.placement.footprint.x_max - data.placement.footprint.x_min"
            :height="data.placement.footprint.y_max - data.placement.footprint.y_min"
            fill="none"
            :stroke="data.placement.exceeds ? '#dc2626' : '#10b981'"
            stroke-width="1.5"
            vector-effect="non-scaling-stroke"
          />
        </svg>
      </div>

      <p class="pointer-events-none absolute bottom-1 right-2 text-[10px] text-slate-500">
        {{ t('sheet.viewHint') }}
      </p>
    </div>

    <p v-if="data.placement.exceeds" class="mt-2 text-xs text-red-400">
      {{ t('sheet.outOfBounds') }}
    </p>
    <p v-if="data.sheetExceedsWorkspace" class="mt-2 text-xs text-amber-300">
      ⚠ {{ t('sheet.exceedsWarning') }}
    </p>
  </div>
</template>

<style scoped>
:deep(foreignObject > div > svg) {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
