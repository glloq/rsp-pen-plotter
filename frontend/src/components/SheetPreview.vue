<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import DOMPurify from 'dompurify'
import { useJobStore } from '../stores/job'
import { computePlacement, unionBounds } from '../lib/placement'

const { t } = useI18n()
const store = useJobStore()

// Aggregate everything the preview needs in one computed so the template
// can early-out cleanly. We rebuild this whenever the upload, profile,
// scale-mode, margin or user-defined drawing region changes.
const data = computed(() => {
  const profile = store.selectedProfile
  if (!profile || store.layers.length === 0) return null
  const bounds = unionBounds(store.layers.map((l) => l.bbox))
  if (!bounds) return null
  const ws = profile.workspace
  const wsW = ws.x_max - ws.x_min
  const wsH = ws.y_max - ws.y_min
  if (wsW <= 0 || wsH <= 0) return null
  const userRegion = store.currentDrawing
  // Default = auto-fit via the legacy ``computePlacement`` path. When the
  // user has dragged/resized, snap the visible drawing rect to their
  // explicit ``drawingRegion`` and disable the legacy scale-mode logic.
  let footprint: { x_min: number; y_min: number; x_max: number; y_max: number }
  let widthMm: number
  let heightMm: number
  let scale: number
  let exceeds: boolean
  if (userRegion) {
    footprint = {
      x_min: ws.x_min + userRegion.x_mm,
      y_min: ws.y_min + userRegion.y_mm,
      x_max: ws.x_min + userRegion.x_mm + userRegion.width_mm,
      y_max: ws.y_min + userRegion.y_mm + userRegion.height_mm,
    }
    widthMm = userRegion.width_mm
    heightMm = userRegion.height_mm
    const span = Math.max(bounds.x_max - bounds.x_min, 1e-9)
    scale = widthMm / span
    exceeds
      = footprint.x_min < ws.x_min - 0.01
      || footprint.y_min < ws.y_min - 0.01
      || footprint.x_max > ws.x_max + 0.01
      || footprint.y_max > ws.y_max + 0.01
  } else {
    const placement = computePlacement(bounds, profile, store.scaleMode, store.marginMm)
    footprint = placement.footprint
    widthMm = placement.widthMm
    heightMm = placement.heightMm
    scale = placement.scale
    exceeds = placement.exceeds
  }
  const pad = Math.max(wsW, wsH) * 0.04
  return { profile, ws, wsW, wsH, pad, footprint, widthMm, heightMm, scale, exceeds, userRegion }
})

const scaleLabel = computed(() => {
  if (!data.value) return ''
  if (store.scaleMode === 'actual' && !data.value.userRegion) return '1:1'
  return `${(data.value.scale * 100).toFixed(0)}%`
})

// View transform — independent from the drawing scale; this is just how the
// user is looking at the workspace (zoom/pan inside the preview pane).
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)

function resetView(): void {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
}

watch(() => store.job?.job_id, () => resetView())
watch(() => store.selectedProfileName, () => resetView())

// Pointer interaction state. ``mode`` selects which gesture is in progress
// so a single set of event handlers can drive view-pan, drawing-move and
// handle-resize. ``handle`` identifies which resize anchor is grabbed.
type Mode = 'idle' | 'pan-view' | 'move-drawing' | 'resize'
const mode = ref<Mode>('idle')
const handle = ref<'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | null>(null)
const container = ref<HTMLDivElement | null>(null)
let startPxX = 0
let startPxY = 0
let startRegion: { x_mm: number; y_mm: number; width_mm: number; height_mm: number } | null = null

function pxPerMm(): number {
  const d = data.value
  if (!d || !container.value) return 1
  return container.value.clientWidth / (d.wsW + 2 * d.pad)
}

function regionFromData() {
  const d = data.value
  if (!d) return null
  if (d.userRegion) {
    return { ...d.userRegion }
  }
  // Synthesize a region from the current auto-fit footprint, expressed in
  // workspace-local coordinates (offsets from workspace.x_min/y_min) so the
  // backend payload mapping stays straight.
  return {
    x_mm: d.footprint.x_min - d.ws.x_min,
    y_mm: d.footprint.y_min - d.ws.y_min,
    width_mm: d.widthMm,
    height_mm: d.heightMm,
  }
}

function onWheel(event: WheelEvent): void {
  event.preventDefault()
  const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15
  zoom.value = Math.max(0.2, Math.min(zoom.value * factor, 12))
}

function onPointerDown(event: PointerEvent): void {
  if (event.button !== 0 && event.button !== 1) return
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  startPxX = event.clientX
  startPxY = event.clientY
  startRegion = regionFromData()
  // Decide gesture: if pointer is on a handle, the SVG handlers below
  // already pre-set ``mode``/``handle``. Otherwise fall back to view-pan.
  if (mode.value === 'idle') {
    mode.value = 'pan-view'
  }
}

function onPointerMove(event: PointerEvent): void {
  if (mode.value === 'idle') return
  const dxPx = event.clientX - startPxX
  const dyPx = event.clientY - startPxY
  if (mode.value === 'pan-view') {
    panX.value += event.movementX
    panY.value += event.movementY
    return
  }
  const d = data.value
  if (!d || !startRegion) return
  // Convert pixel delta to workspace-mm delta. Divide by zoom because the
  // wrapper itself is scaled, then by ``pxPerMm`` to leave mm.
  const k = zoom.value * pxPerMm()
  const dxMm = dxPx / k
  const dyMm = dyPx / k
  if (mode.value === 'move-drawing') {
    store.setDrawing({
      x_mm: startRegion.x_mm + dxMm,
      y_mm: startRegion.y_mm + dyMm,
      width_mm: startRegion.width_mm,
      height_mm: startRegion.height_mm,
    })
    return
  }
  if (mode.value === 'resize' && handle.value) {
    const minSize = 5  // mm — don't let the drawing collapse to a point
    let x = startRegion.x_mm
    let y = startRegion.y_mm
    let w = startRegion.width_mm
    let h = startRegion.height_mm
    if (handle.value.includes('w')) {
      const newW = Math.max(minSize, startRegion.width_mm - dxMm)
      x = startRegion.x_mm + (startRegion.width_mm - newW)
      w = newW
    } else if (handle.value.includes('e')) {
      w = Math.max(minSize, startRegion.width_mm + dxMm)
    }
    if (handle.value.includes('n')) {
      const newH = Math.max(minSize, startRegion.height_mm - dyMm)
      y = startRegion.y_mm + (startRegion.height_mm - newH)
      h = newH
    } else if (handle.value.includes('s')) {
      h = Math.max(minSize, startRegion.height_mm + dyMm)
    }
    store.setDrawing({ x_mm: x, y_mm: y, width_mm: w, height_mm: h })
  }
}

function onPointerUp(event: PointerEvent): void {
  mode.value = 'idle'
  handle.value = null
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
}

// These set ``mode`` *before* the event bubbles up to the container, where
// ``onPointerDown`` does the setPointerCapture + records the start point.
// We deliberately don't call ``stopPropagation`` — without the container's
// capture we'd lose pointermove events the moment the cursor leaves the
// rect, killing the drag.
function startMoveDrawing(event: PointerEvent): void {
  if (event.button !== 0) return
  mode.value = 'move-drawing'
}

function startResize(h: typeof handle.value, event: PointerEvent): void {
  if (event.button !== 0) return
  mode.value = 'resize'
  handle.value = h
}

function autoFit(): void {
  store.resetDrawing()
}

// Bake the SVG into a foreignObject inside the preview so the user sees
// the actual drawing — not just its bounding box.
const cleanSvg = computed(() => {
  if (!store.svg) return ''
  return DOMPurify.sanitize(store.svg, { USE_PROFILES: { svg: true, svgFilters: true } })
})

// Cursor that reflects which gesture is currently bound to the pointer.
const containerCursor = computed(() => {
  if (mode.value === 'pan-view') return 'grabbing'
  if (mode.value === 'move-drawing') return 'grabbing'
  if (mode.value === 'resize') return 'crosshair'
  return 'grab'
})

onMounted(resetView)
</script>

<template>
  <div v-if="data" class="flex h-full w-full min-h-0 flex-col gap-2">
    <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-xs">
      <h2 class="uppercase tracking-wide text-slate-400">{{ t('sheet.title') }}</h2>
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-slate-300">
        <span>{{ t('sheet.workArea') }}: {{ data.wsW.toFixed(0) }}×{{ data.wsH.toFixed(0) }} mm</span>
        <span>
          {{ t('sheet.drawing') }}:
          {{ data.widthMm.toFixed(0) }}×{{ data.heightMm.toFixed(0) }} mm
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
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300 hover:bg-slate-800"
          :title="t('sheet.autoFitHint')"
          @click="autoFit"
        >
          {{ t('sheet.autoFit') }}
        </button>
      </div>
    </div>

    <div
      ref="container"
      class="relative min-h-0 flex-1 overflow-hidden rounded border border-slate-700 bg-slate-900/40 select-none"
      :style="{ touchAction: 'none', cursor: containerCursor }"
      @wheel="onWheel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
    >
      <div
        class="absolute inset-0"
        :style="{ transform: `translate(${panX}px, ${panY}px) scale(${zoom})`, transformOrigin: '50% 50%' }"
      >
        <svg
          :viewBox="`${data.ws.x_min - data.pad} ${data.ws.y_min - data.pad} ${data.wsW + 2 * data.pad} ${data.wsH + 2 * data.pad}`"
          class="h-full w-full"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          :aria-label="t('sheet.title')"
        >
          <!-- Workspace = the machine's physical drawable envelope. This IS
               the background; everything else is drawn on top. -->
          <rect
            :x="data.ws.x_min"
            :y="data.ws.y_min"
            :width="data.wsW"
            :height="data.wsH"
            fill="#ffffff"
            stroke="#475569"
            stroke-width="1"
            vector-effect="non-scaling-stroke"
          />
          <!-- Margin guide (only meaningful when auto-fit is on). -->
          <rect
            v-if="!data.userRegion && store.scaleMode === 'fit' && store.marginMm > 0"
            :x="data.ws.x_min + store.marginMm"
            :y="data.ws.y_min + store.marginMm"
            :width="Math.max(data.wsW - 2 * store.marginMm, 0)"
            :height="Math.max(data.wsH - 2 * store.marginMm, 0)"
            fill="none"
            stroke="#cbd5e1"
            stroke-width="1"
            stroke-dasharray="4 3"
            vector-effect="non-scaling-stroke"
          />
          <!-- Drawing preview (the actual SVG) inside its placement bbox. -->
          <foreignObject
            v-if="cleanSvg"
            :x="data.footprint.x_min"
            :y="data.footprint.y_min"
            :width="Math.max(data.footprint.x_max - data.footprint.x_min, 0.01)"
            :height="Math.max(data.footprint.y_max - data.footprint.y_min, 0.01)"
          >
            <div
              xmlns="http://www.w3.org/1999/xhtml"
              class="h-full w-full overflow-hidden pointer-events-none"
              v-html="cleanSvg"
            />
          </foreignObject>
          <!-- Interactive bbox: drag the interior to move, drag a corner/edge
               handle to resize. -->
          <rect
            :x="data.footprint.x_min"
            :y="data.footprint.y_min"
            :width="data.footprint.x_max - data.footprint.x_min"
            :height="data.footprint.y_max - data.footprint.y_min"
            :fill="'transparent'"
            :stroke="data.exceeds ? '#dc2626' : '#10b981'"
            stroke-width="1.5"
            vector-effect="non-scaling-stroke"
            style="cursor: grab;"
            @pointerdown="startMoveDrawing"
          />
          <!-- Eight handles. The radius is set in screen pixels via
               ``vector-effect`` so they stay the same size when zoomed. -->
          <g v-if="data" :stroke="data.exceeds ? '#dc2626' : '#10b981'" fill="#0f172a" stroke-width="1.5">
            <template v-for="h in (['nw','n','ne','e','se','s','sw','w'] as const)" :key="h">
              <circle
                :cx="h.includes('w') ? data.footprint.x_min : h.includes('e') ? data.footprint.x_max : (data.footprint.x_min + data.footprint.x_max) / 2"
                :cy="h.includes('n') ? data.footprint.y_min : h.includes('s') ? data.footprint.y_max : (data.footprint.y_min + data.footprint.y_max) / 2"
                r="5"
                vector-effect="non-scaling-stroke"
                :style="{ cursor: (h === 'n' || h === 's') ? 'ns-resize' : (h === 'e' || h === 'w') ? 'ew-resize' : (h === 'nw' || h === 'se') ? 'nwse-resize' : 'nesw-resize' }"
                @pointerdown="(e) => startResize(h, e)"
              />
            </template>
          </g>
        </svg>
      </div>

      <p class="pointer-events-none absolute bottom-1 right-2 text-[10px] text-slate-500">
        {{ t('sheet.viewHint') }}
      </p>
    </div>

    <p v-if="data.exceeds" class="text-xs text-red-400">
      {{ t('sheet.outOfBounds') }}
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
