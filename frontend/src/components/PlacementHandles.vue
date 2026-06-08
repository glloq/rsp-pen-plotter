<script setup lang="ts">
// Interactive bounding-box + resize handles + page/variant chip for
// each placement on the sheet (L10 #2 extract).
//
// Owns the pointer gesture state machine (idle / move / resize) for
// placement edits. Live mutations during drag are emitted as
// ``move`` / ``resize`` intents — the orchestrator forwards them
// to ``store.setDrawing`` so the canvas updates in lock-step. The
// component never touches the store directly, which keeps the gesture
// logic deterministic + unit-testable in isolation.
//
// Rendered inside the same ``<svg>`` as the SheetCanvas content so
// the bounding rects share the workspace coordinate system without
// any extra transform math.

import { onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { RenderedPlacement } from '../composables/useSheetGeometry'

const { t } = useI18n()

const props = defineProps<{
  renderedPlacements: RenderedPlacement[]
  selectedPlacementId: string | null
  /** Multiplier turning client-pixel deltas into mm: typically
   *  ``zoom * pxPerMm()``. Passed in so the gesture math stays
   *  decoupled from the geometry composable. */
  pxToMm: () => number
  snap: (value: number) => number
  /** True when ``snapMm > 0`` — used to clamp the resize lower bound
   *  to a snap multiple instead of the raw 5mm floor. */
  snapActive: boolean
  /** When true, resize gestures preserve the placement's original
   *  width:height ratio. Corner handles drive a uniform scale; edge
   *  handles derive the other dimension from the dragged one. */
  aspectLock: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
  /** Live move during drag — position only, so a reposition never
   *  touches the placement's width/height (proportions stay fixed).
   *  Orchestrator forwards to setDrawing. */
  move: [
    {
      id: string
      x_mm: number
      y_mm: number
    },
  ]
  /** Live resize during drag — same shape as ``move``. */
  resize: [
    {
      id: string
      x_mm: number
      y_mm: number
      width_mm: number
      height_mm: number
    },
  ]
  doubleClick: [id: string]
  pageChange: [{ id: string; page: number }]
  remove: [id: string]
}>()

type Handle = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | null
type Mode = 'idle' | 'move-drawing' | 'resize'

const mode = ref<Mode>('idle')
const handle = ref<Handle>(null)
const activePlacementId = ref<string | null>(null)
let startPxX = 0
let startPxY = 0
let startRegion: { x_mm: number; y_mm: number; width_mm: number; height_mm: number } | null = null

function findRect(id: string) {
  return props.renderedPlacements.find((rp) => rp.placement.id === id)
}

function startMoveDrawing(event: PointerEvent, id: string): void {
  if (event.button !== 0) return
  // The bounding-rect ``<rect>`` already has pointer capture from
  // ``onPointerDown`` below; we only need to record the gesture
  // intent + the starting placement region.
  const rp = findRect(id)
  if (!rp) return
  mode.value = 'move-drawing'
  activePlacementId.value = id
  startPxX = event.clientX
  startPxY = event.clientY
  startRegion = {
    x_mm: rp.placement.x_mm,
    y_mm: rp.placement.y_mm,
    width_mm: rp.placement.width_mm,
    height_mm: rp.placement.height_mm,
  }
  ;(event.currentTarget as Element).setPointerCapture(event.pointerId)
  emit('select', id)
}

function startResize(h: Exclude<Handle, null>, event: PointerEvent, id: string): void {
  if (event.button !== 0) return
  const rp = findRect(id)
  if (!rp) return
  mode.value = 'resize'
  handle.value = h
  activePlacementId.value = id
  startPxX = event.clientX
  startPxY = event.clientY
  startRegion = {
    x_mm: rp.placement.x_mm,
    y_mm: rp.placement.y_mm,
    width_mm: rp.placement.width_mm,
    height_mm: rp.placement.height_mm,
  }
  ;(event.currentTarget as Element).setPointerCapture(event.pointerId)
  emit('select', id)
}

// Pointer events can fire faster than the display refresh (120 Hz+ on
// some trackpads / pens). Each one would otherwise push a store mutation
// → reactive recompute (renderedPlacements) → re-render of the whole
// sheet. Coalesce them: record the latest position and apply at most
// once per animation frame so the work tracks the paint rate, not the
// input rate.
let pendingX = 0
let pendingY = 0
let moveRaf = 0

function onPointerMove(event: PointerEvent): void {
  if (mode.value === 'idle' || !startRegion || !activePlacementId.value) return
  pendingX = event.clientX
  pendingY = event.clientY
  if (moveRaf === 0) moveRaf = requestAnimationFrame(flushMove)
}

function flushMove(): void {
  moveRaf = 0
  applyMove(pendingX, pendingY)
}

function applyMove(clientX: number, clientY: number): void {
  if (mode.value === 'idle' || !startRegion || !activePlacementId.value) return
  const k = props.pxToMm()
  if (k <= 0) return
  const dxMm = (clientX - startPxX) / k
  const dyMm = (clientY - startPxY) / k
  if (mode.value === 'move-drawing') {
    emit('move', {
      id: activePlacementId.value,
      x_mm: props.snap(startRegion.x_mm + dxMm),
      y_mm: props.snap(startRegion.y_mm + dyMm),
    })
    return
  }
  if (mode.value === 'resize' && handle.value) {
    const minSize = 5
    let x = startRegion.x_mm
    let y = startRegion.y_mm
    let w = startRegion.width_mm
    let h = startRegion.height_mm
    const isCornerHandle = handle.value.length === 2
    const aspect = startRegion.height_mm > 0 ? startRegion.width_mm / startRegion.height_mm : 1
    if (props.aspectLock && isCornerHandle) {
      // Corner drag with the ratio locked: pick whichever axis the
      // operator moved more (in proportional terms) and drive both
      // dimensions off it.
      const sxRaw = handle.value.includes('w') ? -dxMm : dxMm
      const syRaw = handle.value.includes('n') ? -dyMm : dyMm
      const candW = startRegion.width_mm + sxRaw
      const candH = startRegion.height_mm + syRaw
      const sW = candW / startRegion.width_mm
      const sH = candH / startRegion.height_mm
      const scale = Math.abs(sW - 1) >= Math.abs(sH - 1) ? sW : sH
      w = Math.max(minSize, startRegion.width_mm * scale)
      h = Math.max(minSize, startRegion.height_mm * scale)
      // Re-clamp the other axis if either hit the floor so the ratio
      // is preserved at the corner of the allowed region.
      if (w === minSize) h = Math.max(minSize, minSize / aspect)
      if (h === minSize) w = Math.max(minSize, minSize * aspect)
      if (handle.value.includes('w')) x = startRegion.x_mm + (startRegion.width_mm - w)
      if (handle.value.includes('n')) y = startRegion.y_mm + (startRegion.height_mm - h)
    } else if (props.aspectLock && !isCornerHandle) {
      // Edge drag with the ratio locked: derive the perpendicular
      // dimension from the dragged one, growing symmetrically around
      // the unchanged axis so the placement doesn't drift sideways.
      if (handle.value === 'w' || handle.value === 'e') {
        w =
          handle.value === 'w'
            ? Math.max(minSize, startRegion.width_mm - dxMm)
            : Math.max(minSize, startRegion.width_mm + dxMm)
        h = Math.max(minSize, w / aspect)
        if (handle.value === 'w') x = startRegion.x_mm + (startRegion.width_mm - w)
        y = startRegion.y_mm + (startRegion.height_mm - h) / 2
      } else {
        h =
          handle.value === 'n'
            ? Math.max(minSize, startRegion.height_mm - dyMm)
            : Math.max(minSize, startRegion.height_mm + dyMm)
        w = Math.max(minSize, h * aspect)
        if (handle.value === 'n') y = startRegion.y_mm + (startRegion.height_mm - h)
        x = startRegion.x_mm + (startRegion.width_mm - w) / 2
      }
    } else {
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
    }
    emit('resize', {
      id: activePlacementId.value,
      x_mm: props.snap(x),
      y_mm: props.snap(y),
      width_mm: props.snapActive ? Math.max(minSize, props.snap(w)) : w,
      height_mm: props.snapActive ? Math.max(minSize, props.snap(h)) : h,
    })
  }
}

function onPointerUp(event: PointerEvent): void {
  if (mode.value === 'idle') return
  // Flush any frame-coalesced move so the committed position is exactly
  // where the operator released, not the last frame boundary.
  if (moveRaf !== 0) {
    cancelAnimationFrame(moveRaf)
    moveRaf = 0
    applyMove(pendingX, pendingY)
  }
  mode.value = 'idle'
  handle.value = null
  activePlacementId.value = null
  startRegion = null
  try {
    ;(event.currentTarget as Element).releasePointerCapture(event.pointerId)
  } catch {
    // Pointer capture may have been released elsewhere (e.g. when
    // the operator drags off the canvas); swallowing keeps the
    // gesture cleanup idempotent.
  }
}

function onDblClick(event: MouseEvent, id: string): void {
  event.stopPropagation()
  emit('doubleClick', id)
}

onBeforeUnmount(() => {
  if (moveRaf !== 0) cancelAnimationFrame(moveRaf)
})

function placementPageCount(p: { upload_metadata: Record<string, unknown> }): number {
  return Number(p.upload_metadata?.page_count ?? 0)
}
function placementCurrentPage(p: { upload_metadata: Record<string, unknown> }): number {
  return Number(p.upload_metadata?.page ?? 0)
}

function handleCursor(h: Exclude<Handle, null>): string {
  if (h === 'n' || h === 's') return 'ns-resize'
  if (h === 'e' || h === 'w') return 'ew-resize'
  if (h === 'nw' || h === 'se') return 'nwse-resize'
  return 'nesw-resize'
}

function handleCx(rp: RenderedPlacement, h: Exclude<Handle, null>): number {
  if (h.includes('w')) return rp.footprint.x_min
  if (h.includes('e')) return rp.footprint.x_max
  return (rp.footprint.x_min + rp.footprint.x_max) / 2
}

function handleCy(rp: RenderedPlacement, h: Exclude<Handle, null>): number {
  if (h.includes('n')) return rp.footprint.y_min
  if (h.includes('s')) return rp.footprint.y_max
  return (rp.footprint.y_min + rp.footprint.y_max) / 2
}

const HANDLES: Exclude<Handle, null>[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']
</script>

<template>
  <g @pointermove="onPointerMove" @pointerup="onPointerUp" @pointercancel="onPointerUp">
    <template v-for="rp in renderedPlacements" :key="rp.placement.id">
      <rect
        :x="rp.footprint.x_min"
        :y="rp.footprint.y_min"
        :width="rp.footprint.x_max - rp.footprint.x_min"
        :height="rp.footprint.y_max - rp.footprint.y_min"
        fill="transparent"
        :stroke="
          rp.exceeds ? '#dc2626' : selectedPlacementId === rp.placement.id ? '#10b981' : '#475569'
        "
        :stroke-width="selectedPlacementId === rp.placement.id ? 2 : 1"
        :stroke-dasharray="selectedPlacementId === rp.placement.id ? undefined : '4 3'"
        vector-effect="non-scaling-stroke"
        style="cursor: grab"
        @pointerdown.stop="(e) => startMoveDrawing(e, rp.placement.id)"
        @dblclick="(e) => onDblClick(e, rp.placement.id)"
      />
      <g
        v-if="selectedPlacementId === rp.placement.id"
        :stroke="rp.exceeds ? '#dc2626' : '#10b981'"
        fill="#0f172a"
        stroke-width="1.5"
      >
        <circle
          v-for="h in HANDLES"
          :key="h"
          :cx="handleCx(rp, h)"
          :cy="handleCy(rp, h)"
          r="5"
          vector-effect="non-scaling-stroke"
          :style="{ cursor: handleCursor(h) }"
          @pointerdown.stop="(e) => startResize(h, e, rp.placement.id)"
        />
      </g>
      <foreignObject
        v-if="selectedPlacementId === rp.placement.id"
        :x="rp.footprint.x_max - 240"
        :y="rp.footprint.y_min - 26"
        width="240"
        height="22"
      >
        <div xmlns="http://www.w3.org/1999/xhtml" class="flex items-center justify-end gap-1">
          <select
            v-if="placementPageCount(rp.placement) > 1"
            class="max-w-[100px] truncate rounded border border-sky-600 bg-sky-950 px-1 py-0.5 text-[11px] text-sky-100 shadow focus:outline-none focus:ring-1 focus:ring-sky-400"
            :value="placementCurrentPage(rp.placement)"
            :title="
              t('upload.pageOf', {
                current: placementCurrentPage(rp.placement) + 1,
                total: placementPageCount(rp.placement),
              })
            "
            :disabled="loading"
            @change="
              (e) =>
                emit('pageChange', {
                  id: rp.placement.id,
                  page: Number((e.target as HTMLSelectElement).value),
                })
            "
            @pointerdown.stop
            @click.stop
            @dblclick.stop
          >
            <option v-for="n in placementPageCount(rp.placement)" :key="n - 1" :value="n - 1">
              {{ t('upload.pageOf', { current: n, total: placementPageCount(rp.placement) }) }}
            </option>
          </select>
          <button
            type="button"
            class="flex h-5 w-5 items-center justify-center rounded bg-red-600 text-[11px] font-bold text-white shadow hover:bg-red-500"
            :title="t('sheet.removePlacement')"
            @click.stop="emit('remove', rp.placement.id)"
            @pointerdown.stop
          >
            ✕
          </button>
        </div>
      </foreignObject>
    </template>
  </g>
</template>
