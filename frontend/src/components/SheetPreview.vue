<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import DOMPurify from 'dompurify'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'
import { computePlacement, unionBounds } from '../lib/placement'

const { t } = useI18n()
const store = useJobStore()
const ui = useUiStore()

// Workspace data is always available as long as a profile is selected,
// even before any file has been uploaded — so the plan view shows the
// machine envelope and lets the user drop a file straight onto it.
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

// Drawing data is rebuilt whenever the upload, profile, scale-mode,
// margin or user-defined drawing region changes. Null when no file is
// loaded — the workspace + grid still render.
const drawing = computed(() => {
  const w = workspace.value
  if (!w || store.layers.length === 0) return null
  const bounds = unionBounds(store.layers.map((l) => l.bbox))
  if (!bounds) return null
  const userRegion = store.currentDrawing
  let footprint: { x_min: number; y_min: number; x_max: number; y_max: number }
  let widthMm: number
  let heightMm: number
  let scale: number
  let exceeds: boolean
  if (userRegion) {
    footprint = {
      x_min: w.ws.x_min + userRegion.x_mm,
      y_min: w.ws.y_min + userRegion.y_mm,
      x_max: w.ws.x_min + userRegion.x_mm + userRegion.width_mm,
      y_max: w.ws.y_min + userRegion.y_mm + userRegion.height_mm,
    }
    widthMm = userRegion.width_mm
    heightMm = userRegion.height_mm
    const span = Math.max(bounds.x_max - bounds.x_min, 1e-9)
    scale = widthMm / span
    exceeds
      = footprint.x_min < w.ws.x_min - 0.01
      || footprint.y_min < w.ws.y_min - 0.01
      || footprint.x_max > w.ws.x_max + 0.01
      || footprint.y_max > w.ws.y_max + 0.01
  } else {
    const placement = computePlacement(bounds, w.profile, store.scaleMode, store.marginMm)
    footprint = placement.footprint
    widthMm = placement.widthMm
    heightMm = placement.heightMm
    scale = placement.scale
    exceeds = placement.exceeds
  }
  return { footprint, widthMm, heightMm, scale, exceeds, userRegion, bounds }
})

// Grid spacing: minor lines every 10 mm (1 cm), major every 50 mm (5 cm),
// labels every 50 mm showing the value in cm.
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

const scaleLabel = computed(() => {
  if (!drawing.value) return ''
  if (store.scaleMode === 'actual' && !drawing.value.userRegion) return '1:1'
  return `${(drawing.value.scale * 100).toFixed(0)}%`
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

// Pointer interaction state.
type Mode = 'idle' | 'pan-view' | 'move-drawing' | 'resize'
const mode = ref<Mode>('idle')
const handle = ref<'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | null>(null)
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

function regionFromData() {
  const d = drawing.value
  const w = workspace.value
  if (!d || !w) return null
  if (d.userRegion) return { ...d.userRegion }
  return {
    x_mm: d.footprint.x_min - w.ws.x_min,
    y_mm: d.footprint.y_min - w.ws.y_min,
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
  const d = drawing.value
  if (!d || !startRegion) return
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
    store.setDrawing({ x_mm: x, y_mm: y, width_mm: w, height_mm: h })
  }
}

function onPointerUp(event: PointerEvent): void {
  mode.value = 'idle'
  handle.value = null
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
}

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

// Drag-and-drop from the FilesPane: the file row sets a custom MIME type
// in dataTransfer so we can recognise it here and centre the drawing on
// the drop point. If the drop happens before a file is loaded, we just
// pop the edit modal so the user can pick a file.
const dragOver = ref(false)

function onDragEnter(event: DragEvent): void {
  if (event.dataTransfer?.types.includes('application/x-omniplot-file')) {
    event.preventDefault()
    dragOver.value = true
  }
}
function onDragOver(event: DragEvent): void {
  if (event.dataTransfer?.types.includes('application/x-omniplot-file')) {
    event.preventDefault()
    dragOver.value = true
  }
}
function onDragLeave(event: DragEvent): void {
  if (event.currentTarget === event.target) dragOver.value = false
}

function clientToSvgMm(clientX: number, clientY: number): { x: number; y: number } | null {
  // Translate a screen pixel into workspace mm using the SVG's CTM, so
  // the drop point is exact regardless of zoom/pan state.
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

function onDrop(event: DragEvent): void {
  event.preventDefault()
  dragOver.value = false
  if (!event.dataTransfer?.types.includes('application/x-omniplot-file')) return
  const d = drawing.value
  const w = workspace.value
  if (!w) {
    // No workspace yet — just open the modal so user can upload.
    ui.openEditModal()
    return
  }
  if (!d) {
    // File hasn't been converted yet — open the modal so user can finish.
    ui.openEditModal()
    return
  }
  // Centre the drawing on the drop point, in workspace-relative mm.
  const local = clientToSvgMm(event.clientX, event.clientY)
  if (!local) return
  const newCx = local.x
  const newCy = local.y
  const region = regionFromData()
  if (!region) return
  store.setDrawing({
    x_mm: Math.max(0, newCx - region.width_mm / 2 - w.ws.x_min),
    y_mm: Math.max(0, newCy - region.height_mm / 2 - w.ws.y_min),
    width_mm: region.width_mm,
    height_mm: region.height_mm,
  })
}

const cleanSvg = computed(() => {
  if (!store.svg) return ''
  return DOMPurify.sanitize(store.svg, { USE_PROFILES: { svg: true, svgFilters: true } })
})

const containerCursor = computed(() => {
  if (mode.value === 'pan-view') return 'grabbing'
  if (mode.value === 'move-drawing') return 'grabbing'
  if (mode.value === 'resize') return 'crosshair'
  return 'grab'
})

// Header Generate button — wires into the same store action as the
// modal's Generate section but lives in the plan header so the operator
// can fire G-code without reopening the modal.
const canGenerate = computed(
  () =>
    Boolean(store.svg)
    && store.layers.length > 0
    && store.missingPenSlots.length === 0
    && !store.generating,
)

async function generateAndShow(): Promise<void> {
  await store.generate()
  if (store.gcode) {
    ui.canvasTab = store.selectedProfile?.gcode_dialect === 'ebb' ? 'gcode' : 'simulator'
  }
}

onMounted(resetView)
</script>

<template>
  <div v-if="workspace" class="flex h-full w-full min-h-0 flex-col gap-2">
    <header class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-xs">
      <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 class="uppercase tracking-wide text-slate-400">{{ t('sheet.title') }}</h2>
        <span class="font-mono text-slate-300">
          {{ t('sheet.workArea') }}: {{ workspace.wsW.toFixed(0) }}×{{ workspace.wsH.toFixed(0) }} mm
        </span>
        <span v-if="drawing" class="font-mono text-slate-300">
          {{ t('sheet.drawing') }}: {{ drawing.widthMm.toFixed(0) }}×{{ drawing.heightMm.toFixed(0) }} mm
        </span>
        <span v-if="drawing" class="font-mono text-slate-300">{{ t('sheet.scale') }}: {{ scaleLabel }}</span>
        <span class="font-mono text-slate-400">{{ t('sheet.view') }}: {{ Math.round(zoom * 100) }}%</span>
      </div>
      <div class="flex items-center gap-1">
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300 hover:bg-slate-800"
          @click="resetView"
        >
          {{ t('sheet.resetView') }}
        </button>
        <button
          v-if="drawing"
          type="button"
          class="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300 hover:bg-slate-800"
          :title="t('sheet.autoFitHint')"
          @click="autoFit"
        >
          {{ t('sheet.autoFit') }}
        </button>
        <button
          type="button"
          class="ml-2 rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
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
          <!-- Workspace = the machine's physical drawable envelope. -->
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
          <!-- Grid (minor every 1 cm, major every 5 cm). Labels show cm. -->
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
            <!-- cm labels along the top and left edges -->
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
          <!-- Margin guide (only meaningful when auto-fit is on). -->
          <rect
            v-if="drawing && !drawing.userRegion && store.scaleMode === 'fit' && store.marginMm > 0"
            :x="workspace.ws.x_min + store.marginMm"
            :y="workspace.ws.y_min + store.marginMm"
            :width="Math.max(workspace.wsW - 2 * store.marginMm, 0)"
            :height="Math.max(workspace.wsH - 2 * store.marginMm, 0)"
            fill="none"
            stroke="#94a3b8"
            stroke-width="1"
            stroke-dasharray="4 3"
            vector-effect="non-scaling-stroke"
          />
          <!-- Drawing preview inside its placement bbox. -->
          <foreignObject
            v-if="drawing && cleanSvg"
            :x="drawing.footprint.x_min"
            :y="drawing.footprint.y_min"
            :width="Math.max(drawing.footprint.x_max - drawing.footprint.x_min, 0.01)"
            :height="Math.max(drawing.footprint.y_max - drawing.footprint.y_min, 0.01)"
          >
            <div
              xmlns="http://www.w3.org/1999/xhtml"
              class="h-full w-full overflow-hidden pointer-events-none"
              v-html="cleanSvg"
            />
          </foreignObject>
          <!-- Interactive bbox + handles. -->
          <template v-if="drawing">
            <rect
              :x="drawing.footprint.x_min"
              :y="drawing.footprint.y_min"
              :width="drawing.footprint.x_max - drawing.footprint.x_min"
              :height="drawing.footprint.y_max - drawing.footprint.y_min"
              fill="transparent"
              :stroke="drawing.exceeds ? '#dc2626' : '#10b981'"
              stroke-width="1.5"
              vector-effect="non-scaling-stroke"
              style="cursor: grab;"
              @pointerdown="startMoveDrawing"
            />
            <g :stroke="drawing.exceeds ? '#dc2626' : '#10b981'" fill="#0f172a" stroke-width="1.5">
              <template v-for="h in (['nw','n','ne','e','se','s','sw','w'] as const)" :key="h">
                <circle
                  :cx="h.includes('w') ? drawing.footprint.x_min : h.includes('e') ? drawing.footprint.x_max : (drawing.footprint.x_min + drawing.footprint.x_max) / 2"
                  :cy="h.includes('n') ? drawing.footprint.y_min : h.includes('s') ? drawing.footprint.y_max : (drawing.footprint.y_min + drawing.footprint.y_max) / 2"
                  r="5"
                  vector-effect="non-scaling-stroke"
                  :style="{ cursor: (h === 'n' || h === 's') ? 'ns-resize' : (h === 'e' || h === 'w') ? 'ew-resize' : (h === 'nw' || h === 'se') ? 'nwse-resize' : 'nesw-resize' }"
                  @pointerdown="(e) => startResize(h, e)"
                />
              </template>
            </g>
          </template>
        </svg>
      </div>

      <p class="pointer-events-none absolute bottom-1 right-2 text-[10px] text-slate-500">
        {{ t('sheet.viewHint') }}
      </p>
      <p
        v-if="dragOver"
        class="pointer-events-none absolute inset-0 flex items-center justify-center text-sm font-medium text-emerald-300"
      >
        {{ t('sheet.dropToPosition') }}
      </p>
      <p
        v-if="!drawing && !dragOver"
        class="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-slate-500"
      >
        {{ t('sheet.emptyHint') }}
      </p>
    </div>

    <p v-if="drawing && drawing.exceeds" class="text-xs text-red-400">
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
