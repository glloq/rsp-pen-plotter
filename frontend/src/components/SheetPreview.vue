<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import DOMPurify from 'dompurify'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'
import type { Placement } from '../stores/job'

const { t } = useI18n()
const store = useJobStore()
const ui = useUiStore()

// Workspace data — always available as long as a profile is selected so
// the plan stays visible even without any imported file.
const workspace = computed(() => {
  const profile = store.selectedProfile
  if (!profile) return null
  const ws = profile.workspace
  const wsW = ws.x_max - ws.x_min
  const wsH = ws.y_max - ws.y_min
  if (wsW <= 0 || wsH <= 0) return null
  const pad = Math.max(wsW, wsH) * 0.04
  return { profile, ws, wsW, wsH, pad }
})

// Each placement gets its own rendering rect on the plan. We project
// workspace-relative ``x/y/width/height`` onto absolute machine coords
// using the active profile's origin.
interface RenderedPlacement {
  placement: Placement
  footprint: { x_min: number; y_min: number; x_max: number; y_max: number }
  exceeds: boolean
  cleanSvg: string
}

// DOMPurify.sanitize is expensive on large SVGs; without memoization it
// runs for every placement on every pointer-move during drag, which
// chokes the tab. Cache by placement id + raw svg so unchanged SVGs are
// reused across recomputations. Entries are evicted for placements that
// disappear from the plan.
const sanitizedCache = new Map<string, { svg: string; clean: string }>()

const renderedPlacements = computed<RenderedPlacement[]>(() => {
  const w = workspace.value
  if (!w) return []
  const seen = new Set<string>()
  const out = store.placements.map((p) => {
    seen.add(p.id)
    const x_min = w.ws.x_min + p.x_mm
    const y_min = w.ws.y_min + p.y_mm
    const x_max = x_min + p.width_mm
    const y_max = y_min + p.height_mm
    const exceeds
      = x_min < w.ws.x_min - 0.01
      || y_min < w.ws.y_min - 0.01
      || x_max > w.ws.x_max + 0.01
      || y_max > w.ws.y_max + 0.01
    let cleanSvg = ''
    if (p.svg) {
      const cached = sanitizedCache.get(p.id)
      if (cached && cached.svg === p.svg) {
        cleanSvg = cached.clean
      } else {
        cleanSvg = DOMPurify.sanitize(p.svg, { USE_PROFILES: { svg: true, svgFilters: true } })
        sanitizedCache.set(p.id, { svg: p.svg, clean: cleanSvg })
      }
    } else {
      sanitizedCache.delete(p.id)
    }
    return {
      placement: p,
      footprint: { x_min, y_min, x_max, y_max },
      exceeds,
      cleanSvg,
    }
  })
  for (const id of sanitizedCache.keys()) {
    if (!seen.has(id)) sanitizedCache.delete(id)
  }
  return out
})

const anyExceeds = computed(() => renderedPlacements.value.some((r) => r.exceeds))

// Grid: minor lines every 10 mm (1 cm), major every 50 mm (5 cm).
const grid = computed(() => {
  const w = workspace.value
  if (!w) return null
  const xs: number[] = []
  const ys: number[] = []
  const majorXs: number[] = []
  const majorYs: number[] = []
  const labelsX: { x: number; cm: number }[] = []
  const labelsY: { y: number; cm: number }[] = []
  for (let x = Math.ceil(w.ws.x_min / 10) * 10; x <= w.ws.x_max + 0.0001; x += 10) {
    xs.push(x)
    if (Math.round(x) % 50 === 0) {
      majorXs.push(x)
      labelsX.push({ x, cm: Math.round(x / 10) })
    }
  }
  for (let y = Math.ceil(w.ws.y_min / 10) * 10; y <= w.ws.y_max + 0.0001; y += 10) {
    ys.push(y)
    if (Math.round(y) % 50 === 0) {
      majorYs.push(y)
      labelsY.push({ y, cm: Math.round(y / 10) })
    }
  }
  return { xs, ys, majorXs, majorYs, labelsX, labelsY }
})

// View transform (zoom/pan) is independent of placement scale.
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
function resetView(): void {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
}
function zoomIn(): void {
  zoom.value = Math.min(zoom.value * 1.25, 12)
}
function zoomOut(): void {
  zoom.value = Math.max(zoom.value / 1.25, 0.2)
}
watch(() => store.selectedProfileName, () => resetView())

// Snap-to-grid: 0 = off, otherwise grid step in mm.
const snapMm = ref(0)
const snapOptions = [0, 1, 5, 10]
function snap(value: number): number {
  if (snapMm.value <= 0) return value
  return Math.round(value / snapMm.value) * snapMm.value
}

// Pointer interaction state. The active gesture is bound to whichever
// placement the user grabbed (recorded in ``activePlacementId``).
type Mode = 'idle' | 'pan-view' | 'move-drawing' | 'resize'
const mode = ref<Mode>('idle')
const handle = ref<'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | null>(null)
const activePlacementId = ref<string | null>(null)
const container = ref<HTMLDivElement | null>(null)
const svgEl = ref<SVGSVGElement | null>(null)
let startPxX = 0
let startPxY = 0
let startRegion: { x_mm: number; y_mm: number; width_mm: number; height_mm: number } | null = null

function pxPerMm(): number {
  const w = workspace.value
  if (!w || !container.value) return 1
  return container.value.clientWidth / (w.wsW + 2 * w.pad)
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
  if (mode.value === 'idle') mode.value = 'pan-view'
  else {
    // A placement gesture was pre-armed by its handler — record its
    // current position so the move/resize can compute deltas from it.
    const p = store.placements.find((pl) => pl.id === activePlacementId.value)
    if (p) startRegion = { x_mm: p.x_mm, y_mm: p.y_mm, width_mm: p.width_mm, height_mm: p.height_mm }
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
  if (!startRegion || !activePlacementId.value) return
  const k = zoom.value * pxPerMm()
  const dxMm = dxPx / k
  const dyMm = dyPx / k
  if (mode.value === 'move-drawing') {
    updatePlacementRect(activePlacementId.value, {
      x_mm: snap(startRegion.x_mm + dxMm),
      y_mm: snap(startRegion.y_mm + dyMm),
      width_mm: startRegion.width_mm,
      height_mm: startRegion.height_mm,
    })
    return
  }
  if (mode.value === 'resize' && handle.value) {
    const minSize = 5
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
    updatePlacementRect(activePlacementId.value, {
      x_mm: snap(x),
      y_mm: snap(y),
      width_mm: snapMm.value > 0 ? Math.max(minSize, snap(w)) : w,
      height_mm: snapMm.value > 0 ? Math.max(minSize, snap(h)) : h,
    })
  }
}

function onPointerUp(event: PointerEvent): void {
  mode.value = 'idle'
  handle.value = null
  activePlacementId.value = null
  startRegion = null
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
}

function updatePlacementRect(
  _id: string,
  patch: { x_mm: number; y_mm: number; width_mm: number; height_mm: number },
): void {
  // ``setDrawing`` always edits the selected placement — startMove /
  // startResize already selected the right one on pointer-down.
  store.setDrawing(patch)
}

function startMoveDrawing(event: PointerEvent, id: string): void {
  if (event.button !== 0) return
  mode.value = 'move-drawing'
  activePlacementId.value = id
  store.selectPlacement(id)
}

function startResize(h: typeof handle.value, event: PointerEvent, id: string): void {
  if (event.button !== 0) return
  mode.value = 'resize'
  handle.value = h
  activePlacementId.value = id
  store.selectPlacement(id)
}

// Drag-and-drop from FilesPane: a drag carries either a library file id
// (``application/x-omniplot-library``) — which creates a new placement
// on the plan referencing that library entry — or a placement id
// (``application/x-omniplot-file``) for in-plan duplication / repositioning.
const dragOver = ref(false)
function hasDropPayload(types?: readonly string[]): boolean {
  if (!types) return false
  return (
    types.includes('application/x-omniplot-file') ||
    types.includes('application/x-omniplot-library')
  )
}
function onDragEnter(event: DragEvent): void {
  if (hasDropPayload(event.dataTransfer?.types)) {
    event.preventDefault()
    dragOver.value = true
  }
}
function onDragOver(event: DragEvent): void {
  if (hasDropPayload(event.dataTransfer?.types)) {
    event.preventDefault()
    dragOver.value = true
  }
}
function onDragLeave(event: DragEvent): void {
  if (event.currentTarget === event.target) dragOver.value = false
}

function clientToSvgMm(clientX: number, clientY: number): { x: number; y: number } | null {
  const svg = svgEl.value
  if (!svg) return null
  const pt = svg.createSVGPoint()
  pt.x = clientX
  pt.y = clientY
  const ctm = svg.getScreenCTM()
  if (!ctm) return null
  const local = pt.matrixTransform(ctm.inverse())
  return { x: local.x, y: local.y }
}

async function onDrop(event: DragEvent): Promise<void> {
  event.preventDefault()
  dragOver.value = false
  const w = workspace.value
  if (!w) return
  const local = clientToSvgMm(event.clientX, event.clientY)
  if (!local) return

  // Drop from the library: spawn a new placement bound to that file id.
  const libraryId = event.dataTransfer?.getData('application/x-omniplot-library')
  if (libraryId) {
    const newId = await store.createPlacementFromLibrary(libraryId, {
      x: local.x,
      y: local.y,
    })
    if (newId) store.selectPlacement(newId)
    return
  }

  const sourceId = event.dataTransfer?.getData('application/x-omniplot-file')
  if (!sourceId) return
  const src = store.placements.find((p) => p.id === sourceId)
  if (!src) return
  // If the source placement has no svg yet, the user is just positioning
  // the (empty) draft. Otherwise duplicate it at the drop position.
  if (!src.svg || !src.layers.length) {
    const prev = store.selectedPlacementId
    store.selectPlacement(sourceId)
    store.setDrawing({
      x_mm: Math.max(0, local.x - src.width_mm / 2 - w.ws.x_min),
      y_mm: Math.max(0, local.y - src.height_mm / 2 - w.ws.y_min),
      width_mm: src.width_mm,
      height_mm: src.height_mm,
    })
    if (prev) store.selectPlacement(prev)
    return
  }
  // Duplicate at the drop point, centred on the cursor.
  const newId = store.duplicatePlacement(sourceId)
  if (!newId) return
  const prev = store.selectedPlacementId
  store.selectPlacement(newId)
  store.setDrawing({
    x_mm: Math.max(0, local.x - src.width_mm / 2 - w.ws.x_min),
    y_mm: Math.max(0, local.y - src.height_mm / 2 - w.ws.y_min),
    width_mm: src.width_mm,
    height_mm: src.height_mm,
  })
  if (prev) store.selectPlacement(prev)
}

const containerCursor = computed(() => {
  if (mode.value === 'pan-view') return 'grabbing'
  if (mode.value === 'move-drawing') return 'grabbing'
  if (mode.value === 'resize') return 'crosshair'
  return 'grab'
})

const canGenerate = computed(() => {
  const ready = store.placements.some((p) => p.svg && p.layers.length)
  return ready && store.missingPenSlots.length === 0 && !store.generating
})

async function generateAndShow(): Promise<void> {
  await store.generate()
  if (store.gcode) {
    ui.canvasTab = store.selectedProfile?.gcode_dialect === 'ebb' ? 'gcode' : 'simulator'
  }
}

const placementCount = computed(() => store.placements.filter((p) => p.svg).length)

// Delete / Backspace removes the currently selected placement from the
// plan when the canvas has focus. We ignore the shortcut while the user
// is typing in a field or has a modal/drawer open, since those own their
// own keyboard handling.
function onKey(event: KeyboardEvent): void {
  if (event.key !== 'Delete' && event.key !== 'Backspace') return
  const target = event.target as HTMLElement | null
  if (
    target &&
    (target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.tagName === 'SELECT' ||
      target.isContentEditable)
  ) {
    return
  }
  if (ui.editModalOpen || ui.settingsOpen || ui.plotterDrawerOpen) return
  const id = store.selectedPlacementId
  if (!id) return
  event.preventDefault()
  store.removePlacement(id)
}

onMounted(() => {
  resetView()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div v-if="workspace" class="flex h-full w-full min-h-0 flex-col gap-2">
    <header
      class="flex flex-wrap items-center gap-1 rounded border border-slate-700 bg-slate-900/40 px-2 py-1.5 text-xs"
    >
      <div class="flex items-center gap-1">
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200 hover:bg-slate-800"
          :title="t('sheet.zoomOut')"
          @click="zoomOut"
        >−</button>
        <span class="w-12 text-center font-mono text-slate-300">{{ Math.round(zoom * 100) }}%</span>
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200 hover:bg-slate-800"
          :title="t('sheet.zoomIn')"
          @click="zoomIn"
        >+</button>
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-300 hover:bg-slate-800"
          @click="resetView"
        >
          {{ t('sheet.resetView') }}
        </button>
      </div>

      <div class="h-5 w-px bg-slate-700 mx-1" />

      <div class="flex items-center gap-1">
        <span class="text-slate-500">{{ t('sheet.snap') }}</span>
        <div class="flex overflow-hidden rounded border border-slate-700">
          <button
            v-for="opt in snapOptions"
            :key="opt"
            type="button"
            class="px-2 py-1 transition"
            :class="snapMm === opt
              ? 'bg-slate-700 text-white'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'"
            @click="snapMm = opt"
          >
            {{ opt === 0 ? t('sheet.snapOff') : `${opt} mm` }}
          </button>
        </div>
      </div>

      <div class="ml-auto flex items-center gap-2">
        <span v-if="placementCount" class="font-mono text-slate-400">
          {{ t('sheet.placements', { count: placementCount }) }}
        </span>
        <button
          type="button"
          class="rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="!canGenerate"
          :title="store.missingPenSlots.length ? t('preflight.missingPens', { slots: store.missingPenSlots.join(', ') }) : ''"
          @click="generateAndShow"
        >
          {{ store.generating ? t('layers.generating') : t('layers.generate') }}
        </button>
      </div>
    </header>

    <div
      ref="container"
      class="relative min-h-0 flex-1 overflow-hidden rounded border select-none"
      :class="dragOver ? 'border-emerald-400 bg-emerald-950/30' : 'border-slate-700 bg-slate-900/40'"
      :style="{ touchAction: 'none', cursor: containerCursor }"
      @wheel="onWheel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @dragenter="onDragEnter"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
      <div
        class="absolute inset-0"
        :style="{ transform: `translate(${panX}px, ${panY}px) scale(${zoom})`, transformOrigin: '50% 50%' }"
      >
        <svg
          ref="svgEl"
          :viewBox="`${workspace.ws.x_min - workspace.pad} ${workspace.ws.y_min - workspace.pad} ${workspace.wsW + 2 * workspace.pad} ${workspace.wsH + 2 * workspace.pad}`"
          class="h-full w-full"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          :aria-label="t('sheet.title')"
        >
          <rect
            :x="workspace.ws.x_min"
            :y="workspace.ws.y_min"
            :width="workspace.wsW"
            :height="workspace.wsH"
            fill="#ffffff"
            stroke="#475569"
            stroke-width="1.5"
            vector-effect="non-scaling-stroke"
          />
          <g v-if="grid" pointer-events="none">
            <line
              v-for="x in grid.xs"
              :key="`gx-${x}`"
              :x1="x"
              :x2="x"
              :y1="workspace.ws.y_min"
              :y2="workspace.ws.y_max"
              :stroke="grid.majorXs.includes(x) ? '#cbd5e1' : '#e2e8f0'"
              :stroke-width="grid.majorXs.includes(x) ? 0.8 : 0.5"
              vector-effect="non-scaling-stroke"
            />
            <line
              v-for="y in grid.ys"
              :key="`gy-${y}`"
              :x1="workspace.ws.x_min"
              :x2="workspace.ws.x_max"
              :y1="y"
              :y2="y"
              :stroke="grid.majorYs.includes(y) ? '#cbd5e1' : '#e2e8f0'"
              :stroke-width="grid.majorYs.includes(y) ? 0.8 : 0.5"
              vector-effect="non-scaling-stroke"
            />
            <text
              v-for="label in grid.labelsX"
              :key="`lx-${label.x}`"
              :x="label.x"
              :y="workspace.ws.y_min - 1"
              text-anchor="middle"
              fill="#64748b"
              :font-size="Math.max(workspace.wsW, workspace.wsH) * 0.015"
              font-family="ui-sans-serif, system-ui, sans-serif"
            >
              {{ label.cm }}
            </text>
            <text
              v-for="label in grid.labelsY"
              :key="`ly-${label.y}`"
              :x="workspace.ws.x_min - 1"
              :y="label.y"
              text-anchor="end"
              dominant-baseline="central"
              fill="#64748b"
              :font-size="Math.max(workspace.wsW, workspace.wsH) * 0.015"
              font-family="ui-sans-serif, system-ui, sans-serif"
            >
              {{ label.cm }}
            </text>
          </g>

          <!-- Each placement: drawing content + interactive bbox + handles. -->
          <template v-for="rp in renderedPlacements" :key="rp.placement.id">
            <foreignObject
              v-if="rp.cleanSvg"
              :x="rp.footprint.x_min"
              :y="rp.footprint.y_min"
              :width="Math.max(rp.footprint.x_max - rp.footprint.x_min, 0.01)"
              :height="Math.max(rp.footprint.y_max - rp.footprint.y_min, 0.01)"
            >
              <div
                xmlns="http://www.w3.org/1999/xhtml"
                class="h-full w-full overflow-hidden pointer-events-none"
                v-html="rp.cleanSvg"
              />
            </foreignObject>
            <rect
              :x="rp.footprint.x_min"
              :y="rp.footprint.y_min"
              :width="rp.footprint.x_max - rp.footprint.x_min"
              :height="rp.footprint.y_max - rp.footprint.y_min"
              fill="transparent"
              :stroke="rp.exceeds ? '#dc2626' : store.selectedPlacementId === rp.placement.id ? '#10b981' : '#475569'"
              :stroke-width="store.selectedPlacementId === rp.placement.id ? 2 : 1"
              :stroke-dasharray="store.selectedPlacementId === rp.placement.id ? undefined : '4 3'"
              vector-effect="non-scaling-stroke"
              style="cursor: grab;"
              @pointerdown="(e) => startMoveDrawing(e, rp.placement.id)"
            />
            <g
              v-if="store.selectedPlacementId === rp.placement.id"
              :stroke="rp.exceeds ? '#dc2626' : '#10b981'"
              fill="#0f172a"
              stroke-width="1.5"
            >
              <template v-for="h in (['nw','n','ne','e','se','s','sw','w'] as const)" :key="h">
                <circle
                  :cx="h.includes('w') ? rp.footprint.x_min : h.includes('e') ? rp.footprint.x_max : (rp.footprint.x_min + rp.footprint.x_max) / 2"
                  :cy="h.includes('n') ? rp.footprint.y_min : h.includes('s') ? rp.footprint.y_max : (rp.footprint.y_min + rp.footprint.y_max) / 2"
                  r="5"
                  vector-effect="non-scaling-stroke"
                  :style="{ cursor: (h === 'n' || h === 's') ? 'ns-resize' : (h === 'e' || h === 'w') ? 'ew-resize' : (h === 'nw' || h === 'se') ? 'nwse-resize' : 'nesw-resize' }"
                  @pointerdown="(e) => startResize(h, e, rp.placement.id)"
                />
              </template>
            </g>
            <foreignObject
              v-if="store.selectedPlacementId === rp.placement.id"
              :x="rp.footprint.x_max + 2"
              :y="rp.footprint.y_min - 18"
              width="22"
              height="22"
            >
              <button
                xmlns="http://www.w3.org/1999/xhtml"
                type="button"
                class="flex h-5 w-5 items-center justify-center rounded bg-red-600 text-[11px] font-bold text-white shadow hover:bg-red-500"
                :title="t('sheet.removePlacement')"
                @click.stop="store.removePlacement(rp.placement.id)"
                @pointerdown.stop
              >
                ✕
              </button>
            </foreignObject>
          </template>
        </svg>
      </div>

      <p class="pointer-events-none absolute bottom-1 right-2 text-[10px] text-slate-500">
        {{ t('sheet.viewHint') }}
      </p>
    </div>

    <p v-if="anyExceeds" class="text-xs text-red-400">
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
