<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'
import { parseGcode, type SimBounds, type SimResult } from '../lib/gcode'

const { t } = useI18n()
const store = useJobStore()
const ui = useUiStore()
const { gcode } = storeToRefs(store)

const canvas = ref<HTMLCanvasElement | null>(null)
const sim = ref<SimResult | null>(null)
const playing = ref(false)
const speed = ref(5)
const simTime = ref(0)

const WIDTH = 800
const HEIGHT = 420
const PAD = 20
let raf = 0
let last = 0

const speeds = [1, 5, 100]

// ===== Display options ===================================================
// Each toggle scopes a different piece of information the operator might
// want to inspect on the preview. They all default to "show" so the
// initial view matches the previous behaviour (drawing + travel + pen).
// ``colorFilter`` stores the set of HEX strings to draw; an empty filter
// means "draw all colours" (treated as a wildcard so the user doesn't
// stare at a blank canvas when no tool-change markers were emitted).
const showTravel = ref(true)
const showPenEvents = ref(false)
const showColorChanges = ref(true)
const showPauses = ref(true)
const colorFilter = ref<Set<string>>(new Set())

function toggleColor(hex: string): void {
  const next = new Set(colorFilter.value)
  if (next.has(hex)) next.delete(hex)
  else next.add(hex)
  colorFilter.value = next
  draw()
}

function selectAllColors(): void {
  colorFilter.value = new Set()
  draw()
}

function selectOnlyColor(hex: string): void {
  colorFilter.value = new Set([hex])
  draw()
}

const distinctColors = computed(() => sim.value?.colors ?? [])
const hasColorInfo = computed(() => distinctColors.value.length > 0)

function isColorVisible(hex: string | null): boolean {
  if (colorFilter.value.size === 0) return true
  // Segments emitted before any tool_change marker have ``null`` as their
  // colour. Keep them visible whenever the filter contains a sentinel
  // empty string or matches the actual hex.
  return colorFilter.value.has(hex ?? '')
}

// View transform (zoom/pan) — applied on top of the fit-to-canvas projection.
const viewZoom = ref(1)
const viewPanX = ref(0)
const viewPanY = ref(0)

// Auto-fit to the drawing when it is small relative to the workspace.
// Without this, plotting a 50 mm signature on an A3 bed produces a
// blob of pixels in the corner of the simulator preview — the strokes
// are correct but unreadable. We compute a viewZoom + pan that places
// the drawing's centre at the canvas centre, filling ~80 % of it.
// The base projection still uses workspace bounds so the workspace
// outline stays visible when the user zooms back out.
function resetView(): void {
  const s = sim.value
  const f = frameBounds.value
  const fw = f.maxX - f.minX
  const fh = f.maxY - f.minY
  const bw = s ? s.bounds.maxX - s.bounds.minX : 0
  const bh = s ? s.bounds.maxY - s.bounds.minY : 0
  const meaningful = bw > 1e-3 && bh > 1e-3 && fw > 1e-3 && fh > 1e-3
  const small = meaningful && (bw < fw / 2 || bh < fh / 2)
  if (!small) {
    viewZoom.value = 1
    viewPanX.value = 0
    viewPanY.value = 0
    draw()
    return
  }
  // ``project()`` scales workspace units to the canvas; ``viewZoom``
  // multiplies that. To make the drawing fill ~80 % of the canvas we
  // need (fillRatio * frame / drawing), clamped to the manual zoom
  // limits so very tiny drawings don't disappear past the upper bound.
  const fillRatio = 0.8
  const zoom = Math.max(1, Math.min(12, Math.min((fw * fillRatio) / bw, (fh * fillRatio) / bh)))
  viewZoom.value = zoom
  // Now pan so the drawing's centre lands on the canvas centre. We
  // re-derive the same base scale ``project`` uses (note: NOT the
  // post-zoom scale) and undo the offset that would otherwise leave
  // the drawing where the workspace centre projects to.
  const base = Math.min((WIDTH - 2 * PAD) / fw, (HEIGHT - 2 * PAD) / fh)
  const flip = store.selectedProfile?.origin !== 'top_left'
  const bcx = (s!.bounds.minX + s!.bounds.maxX) / 2
  const bcy = (s!.bounds.minY + s!.bounds.maxY) / 2
  const cxCanvas = PAD + (bcx - f.minX) * base
  const cyCanvas = flip ? PAD + (f.maxY - bcy) * base : PAD + (bcy - f.minY) * base
  viewPanX.value = -(cxCanvas - WIDTH / 2) * zoom
  viewPanY.value = -(cyCanvas - HEIGHT / 2) * zoom
  draw()
}
function zoomIn(): void {
  viewZoom.value = Math.min(viewZoom.value * 1.25, 12)
  draw()
}
function zoomOut(): void {
  viewZoom.value = Math.max(viewZoom.value / 1.25, 0.2)
  draw()
}

// Manual pen change: only relevant on single-pen machines. When enabled,
// every layer is marked ``pause_before='always'`` so the operator gets
// prompted before each colour transition.
const isMultiColor = computed(() => store.isMultiColor)
const allLayers = computed(() => store.placements.flatMap((p) => p.layers))
const manualPenChange = computed<boolean>({
  get: () => allLayers.value.length > 0 && allLayers.value.every((l) => l.pause_before === 'always'),
  set: (value) => {
    const target = value ? 'always' : 'auto'
    const prev = store.selectedPlacementId
    for (const placement of store.placements) {
      const needsChange = placement.layers.some((l) => l.pause_before !== target)
      if (!needsChange) continue
      store.selectPlacement(placement.id)
      for (const layer of placement.layers) {
        if (layer.pause_before !== target) {
          store.updateLayer(layer.layer_id, { pause_before: target })
        }
      }
    }
    if (prev) store.selectPlacement(prev)
  },
})

const frameBounds = computed<SimBounds>(() => {
  const ws = store.selectedProfile?.workspace
  if (ws && ws.x_max > ws.x_min && ws.y_max > ws.y_min) {
    return { minX: ws.x_min, minY: ws.y_min, maxX: ws.x_max, maxY: ws.y_max }
  }
  return sim.value?.bounds ?? { minX: 0, minY: 0, maxX: 1, maxY: 1 }
})

const drawingSize = computed(() => {
  const b = sim.value?.bounds
  if (!b || b.maxX < b.minX) return null
  return { w: b.maxX - b.minX, h: b.maxY - b.minY }
})

const progress = computed(() =>
  sim.value && sim.value.totalTimeSeconds > 0
    ? simTime.value / sim.value.totalTimeSeconds
    : 0,
)

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs.toString().padStart(2, '0')}s`
}

function project(x: number, y: number, b: SimBounds): [number, number] {
  const s = Math.min(
    (WIDTH - 2 * PAD) / Math.max(b.maxX - b.minX, 1e-6),
    (HEIGHT - 2 * PAD) / Math.max(b.maxY - b.minY, 1e-6),
  )
  const flip = store.selectedProfile?.origin !== 'top_left'
  const cx = PAD + (x - b.minX) * s
  const cy = flip ? PAD + (b.maxY - y) * s : PAD + (y - b.minY) * s
  // Apply view transform: zoom around the canvas centre, then translate.
  const zx = (cx - WIDTH / 2) * viewZoom.value + WIDTH / 2 + viewPanX.value
  const zy = (cy - HEIGHT / 2) * viewZoom.value + HEIGHT / 2 + viewPanY.value
  return [zx, zy]
}

function draw(): void {
  const c = canvas.value
  const r = sim.value
  if (!c || !r) return
  const ctx = c.getContext('2d')
  if (!ctx) return
  const dpr = window.devicePixelRatio || 1
  const bw = Math.round(WIDTH * dpr)
  const bh = Math.round(HEIGHT * dpr)
  if (c.width !== bw || c.height !== bh) {
    c.width = bw
    c.height = bh
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  const bounds = frameBounds.value
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, WIDTH, HEIGHT)

  // Sheet / workspace outline.
  const [sx0, sy0] = project(bounds.minX, bounds.minY, bounds)
  const [sx1, sy1] = project(bounds.maxX, bounds.maxY, bounds)
  ctx.strokeStyle = '#94a3b8'
  ctx.lineWidth = 1
  ctx.setLineDash([])
  ctx.strokeRect(
    Math.min(sx0, sx1),
    Math.min(sy0, sy1),
    Math.abs(sx1 - sx0),
    Math.abs(sy1 - sy0),
  )

  const t = simTime.value
  let pen: [number, number] | null = null

  for (const seg of r.segments) {
    if (seg.startTime >= t) break
    // Apply the colour filter — only to drawing segments; travel moves
    // inherit visibility from ``showTravel`` instead because they have
    // no inherent colour.
    if (seg.drawing && !isColorVisible(seg.colorHex)) {
      pen = project(seg.x1, seg.y1, bounds)
      continue
    }
    if (!seg.drawing && !showTravel.value) {
      pen = project(seg.x1, seg.y1, bounds)
      continue
    }
    const frac = seg.duration > 0 ? Math.min(1, (t - seg.startTime) / seg.duration) : 1
    const ex = seg.x0 + (seg.x1 - seg.x0) * frac
    const ey = seg.y0 + (seg.y1 - seg.y0) * frac
    const [ax, ay] = project(seg.x0, seg.y0, bounds)
    const [bx, by] = project(ex, ey, bounds)
    ctx.beginPath()
    ctx.moveTo(ax, ay)
    ctx.lineTo(bx, by)
    if (seg.drawing) {
      // Use the segment's colour when available so a colour-filtered
      // view actually reads as multi-ink; fall back to slate ink when
      // the G-code didn't carry a tool-change marker.
      ctx.strokeStyle = seg.colorHex || '#0f172a'
      ctx.lineWidth = 1.2
      ctx.setLineDash([])
    } else {
      ctx.strokeStyle = '#cbd5e1'
      ctx.lineWidth = 0.6
      ctx.setLineDash([4, 4])
    }
    ctx.stroke()
    ctx.setLineDash([])
    pen = [bx, by]
  }

  // === Event markers =====================================================
  // Plotted on top of the segments so they're never hidden. Each kind
  // gets a distinct glyph + colour so the operator can pick them out
  // without a legend.
  for (const ev of r.events) {
    if (ev.time > t) break
    const [ex, ey] = project(ev.x, ev.y, bounds)
    if (ev.type === 'pen_up' || ev.type === 'pen_down') {
      if (!showPenEvents.value) continue
      drawPenEventMarker(ctx, ex, ey, ev.type === 'pen_up')
    } else if (ev.type === 'tool_change') {
      if (!showColorChanges.value) continue
      drawToolChangeMarker(ctx, ex, ey, ev.colorHex || '#f59e0b')
    } else if (ev.type === 'pause') {
      if (!showPauses.value) continue
      drawPauseMarker(ctx, ex, ey)
    }
  }

  if (pen) {
    ctx.beginPath()
    ctx.arc(pen[0], pen[1], 3, 0, Math.PI * 2)
    ctx.fillStyle = '#10b981'
    ctx.fill()
  }
}

function drawPenEventMarker(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  up: boolean,
): void {
  // Small triangle: pointing up for pen-up, pointing down for pen-down.
  ctx.beginPath()
  if (up) {
    ctx.moveTo(x, y - 4)
    ctx.lineTo(x - 3, y + 2)
    ctx.lineTo(x + 3, y + 2)
  } else {
    ctx.moveTo(x, y + 4)
    ctx.lineTo(x - 3, y - 2)
    ctx.lineTo(x + 3, y - 2)
  }
  ctx.closePath()
  ctx.fillStyle = up ? '#7dd3fc' : '#fcd34d'
  ctx.strokeStyle = '#0f172a'
  ctx.lineWidth = 0.6
  ctx.fill()
  ctx.stroke()
}

function drawToolChangeMarker(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  color: string,
): void {
  ctx.beginPath()
  ctx.arc(x, y, 5, 0, Math.PI * 2)
  ctx.fillStyle = color
  ctx.fill()
  ctx.lineWidth = 1.2
  ctx.strokeStyle = '#0f172a'
  ctx.stroke()
}

function drawPauseMarker(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  // Two vertical bars inside a ring — universal "pause" glyph.
  ctx.beginPath()
  ctx.arc(x, y, 6, 0, Math.PI * 2)
  ctx.fillStyle = '#fef3c7'
  ctx.strokeStyle = '#b45309'
  ctx.lineWidth = 1
  ctx.fill()
  ctx.stroke()
  ctx.fillStyle = '#b45309'
  ctx.fillRect(x - 2.5, y - 3, 1.5, 6)
  ctx.fillRect(x + 1, y - 3, 1.5, 6)
}

function frame(now: number): void {
  const r = sim.value
  if (!playing.value || !r) return
  const dt = (now - last) / 1000
  last = now
  simTime.value = Math.min(r.totalTimeSeconds, simTime.value + dt * speed.value)
  draw()
  if (simTime.value >= r.totalTimeSeconds) {
    playing.value = false
    return
  }
  raf = requestAnimationFrame(frame)
}

function play(): void {
  const r = sim.value
  if (!r) return
  if (simTime.value >= r.totalTimeSeconds) simTime.value = 0
  playing.value = true
  last = performance.now()
  raf = requestAnimationFrame(frame)
}

function pause(): void {
  playing.value = false
  cancelAnimationFrame(raf)
}

function restart(): void {
  pause()
  simTime.value = 0
  draw()
}

function jumpToEnd(): void {
  const r = sim.value
  if (!r) return
  pause()
  simTime.value = r.totalTimeSeconds
  draw()
}

function reparse(): void {
  pause()
  const profile = store.selectedProfile
  const code = gcode.value
  if (!code || !profile) {
    sim.value = null
    return
  }
  sim.value = parseGcode(code, {
    penUpCommand: profile.pen_up_command,
    penDownCommand: profile.pen_down_command,
    travelSpeedMmS: profile.travel_speed_mm_s,
    defaultDrawSpeedMmS: profile.drawing_speed_mm_s,
    toolChangeCommand: profile.tool_change_command,
  })
  // Reset colour filter on every reparse — chips for the previous plot's
  // colours would otherwise hide every segment of the new one.
  colorFilter.value = new Set()
  // Default to the final frame so the operator sees the full result the
  // moment they open the tab. Press Restart / Play to scrub back to the
  // start of the plot.
  simTime.value = sim.value.totalTimeSeconds
  resetView()
}

// When the operator switches into the simulator tab, jump straight to
// the end of the plot and recentre on the workspace — the default view
// shows the finished drawing, not an empty canvas.
watch(
  () => ui.canvasTab,
  (tab) => {
    if (tab !== 'simulator' || !sim.value) return
    pause()
    simTime.value = sim.value.totalTimeSeconds
    resetView()
  },
)

// Pan/zoom interaction on the canvas.
const isPanning = ref(false)
let panStartX = 0
let panStartY = 0
let panOriginX = 0
let panOriginY = 0

function onCanvasWheel(event: WheelEvent): void {
  event.preventDefault()
  const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15
  viewZoom.value = Math.max(0.2, Math.min(viewZoom.value * factor, 12))
  draw()
}

function onCanvasPointerDown(event: PointerEvent): void {
  if (event.button !== 0 && event.button !== 1) return
  isPanning.value = true
  panStartX = event.clientX
  panStartY = event.clientY
  panOriginX = viewPanX.value
  panOriginY = viewPanY.value
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function onCanvasPointerMove(event: PointerEvent): void {
  if (!isPanning.value) return
  viewPanX.value = panOriginX + (event.clientX - panStartX)
  viewPanY.value = panOriginY + (event.clientY - panStartY)
  draw()
}

function onCanvasPointerUp(event: PointerEvent): void {
  isPanning.value = false
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
}

// Display-option toggles update the canvas immediately so the operator
// gets instant feedback. ``deep`` isn't needed: each ref is replaced
// outright when a toggle flips or the colour filter is rebuilt.
watch([showTravel, showPenEvents, showColorChanges, showPauses, colorFilter], () => draw())

watch(gcode, () => reparse())
onMounted(() => reparse())
onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <section v-if="sim" class="flex h-full min-h-0 flex-col rounded-lg border border-slate-700 bg-slate-800/60">
    <!-- Single compact toolbar — playback, zoom and display toggles all
         live on the same row. The zoom group is rendered with a heavier
         border + larger glyphs so it remains the most visually obvious
         control cluster (operators reach for it constantly during scrub
         playback). Display toggles are pill buttons that highlight when
         active, which fits more controls in less vertical space than a
         checkbox grid did. -->
    <div class="flex flex-wrap items-center gap-1.5 border-b border-slate-700 px-3 py-1.5 text-xs">
      <button
        type="button"
        class="rounded bg-emerald-600 hover:bg-emerald-500 px-2.5 py-1 font-medium text-white"
        @click="playing ? pause() : play()"
      >
        {{ playing ? t('simulator.pause') : t('simulator.play') }}
      </button>
      <button
        type="button"
        class="rounded bg-slate-700 hover:bg-slate-600 px-2 py-1 text-slate-100"
        :title="t('simulator.restart')"
        @click="restart"
      >⟲</button>
      <button
        v-for="s in speeds"
        :key="s"
        type="button"
        class="rounded px-1.5 py-1 font-mono"
        :class="speed === s ? 'bg-sky-600 text-white' : 'bg-slate-700 text-slate-200 hover:bg-slate-600'"
        @click="speed = s"
      >
        {{ s }}×
      </button>
      <button
        type="button"
        class="rounded bg-slate-700 hover:bg-slate-600 px-2 py-1 text-slate-100"
        :title="t('simulator.end')"
        @click="jumpToEnd"
      >⏭</button>

      <!-- Zoom cluster — boxed, bold, slightly taller than its neighbours. -->
      <div
        class="ml-1 flex items-center gap-0.5 rounded-md border border-sky-700/70 bg-slate-900 px-0.5 py-0.5 shadow-sm"
      >
        <button
          type="button"
          class="rounded px-2 py-0.5 text-base font-bold text-sky-200 hover:bg-slate-800"
          :title="t('simulator.zoomOut')"
          @click="zoomOut"
        >−</button>
        <span class="w-11 text-center font-mono text-[11px] text-slate-300">{{ Math.round(viewZoom * 100) }}%</span>
        <button
          type="button"
          class="rounded px-2 py-0.5 text-base font-bold text-sky-200 hover:bg-slate-800"
          :title="t('simulator.zoomIn')"
          @click="zoomIn"
        >+</button>
        <button
          type="button"
          class="rounded px-1.5 py-0.5 text-slate-200 hover:bg-slate-800"
          :title="t('simulator.resetView')"
          @click="resetView"
        >⤢</button>
      </div>

      <!-- Display toggles as pill buttons. Each pill highlights with a
           colour that matches its marker glyph on the canvas so the
           legend is implicit (travel = sky, pen events = amber, etc.). -->
      <button
        type="button"
        class="rounded border px-1.5 py-1"
        :class="showTravel
          ? 'border-sky-500 bg-sky-600/30 text-sky-100'
          : 'border-slate-700 bg-slate-900 text-slate-400 hover:bg-slate-800'"
        :title="t('simulator.optTravel')"
        @click="showTravel = !showTravel"
      >⤳</button>
      <button
        type="button"
        class="rounded border px-1.5 py-1"
        :class="showPenEvents
          ? 'border-amber-500 bg-amber-600/30 text-amber-100'
          : 'border-slate-700 bg-slate-900 text-slate-400 hover:bg-slate-800'"
        :title="t('simulator.optPenEvents')"
        @click="showPenEvents = !showPenEvents"
      >▲▼</button>
      <button
        type="button"
        class="rounded border px-1.5 py-1"
        :class="showColorChanges
          ? 'border-emerald-500 bg-emerald-600/30 text-emerald-100'
          : 'border-slate-700 bg-slate-900 text-slate-400 hover:bg-slate-800'"
        :title="t('simulator.optColorChanges')"
        @click="showColorChanges = !showColorChanges"
      >●</button>
      <button
        type="button"
        class="rounded border px-1.5 py-1"
        :class="showPauses
          ? 'border-amber-500 bg-amber-600/30 text-amber-100'
          : 'border-slate-700 bg-slate-900 text-slate-400 hover:bg-slate-800'"
        :title="t('simulator.optPauses')"
        @click="showPauses = !showPauses"
      >❚❚</button>

      <label
        v-if="!isMultiColor"
        class="ml-auto flex items-center gap-1.5 text-slate-300"
        :title="t('simulator.manualPenChangeHint')"
      >
        <input
          type="checkbox"
          :checked="manualPenChange"
          class="h-3.5 w-3.5 accent-emerald-500"
          @change="(e) => (manualPenChange = (e.target as HTMLInputElement).checked)"
        />
        {{ t('simulator.manualPenChange') }}
      </label>
    </div>

    <div
      v-if="hasColorInfo"
      class="flex flex-wrap items-center gap-2 border-b border-slate-700 px-4 py-1.5 text-xs"
    >
      <span class="font-medium uppercase tracking-wide text-slate-500">
        {{ t('simulator.colors') }}
      </span>
      <button
        type="button"
        class="rounded border border-slate-700 px-2 py-0.5 text-slate-200 hover:bg-slate-800"
        :class="colorFilter.size === 0 ? 'bg-slate-700' : 'bg-slate-900'"
        @click="selectAllColors"
      >
        {{ t('simulator.colorAll') }}
      </button>
      <button
        v-for="c in distinctColors"
        :key="c.hex || c.label"
        type="button"
        class="flex items-center gap-1.5 rounded border px-2 py-0.5"
        :class="
          colorFilter.size === 0 || colorFilter.has(c.hex)
            ? 'border-slate-500 bg-slate-700 text-slate-100'
            : 'border-slate-700 bg-slate-900 text-slate-400'
        "
        :title="t('simulator.colorClickHint')"
        @click="toggleColor(c.hex)"
        @dblclick="selectOnlyColor(c.hex)"
      >
        <span
          class="inline-block h-3 w-3 rounded-sm border border-slate-600"
          :style="{ backgroundColor: c.hex || '#94a3b8' }"
          aria-hidden="true"
        />
        <span class="font-mono">{{ c.label || c.hex || '—' }}</span>
        <span class="text-slate-500">({{ c.segmentCount }})</span>
      </button>
    </div>

    <canvas
      ref="canvas"
      :width="WIDTH"
      :height="HEIGHT"
      class="w-full bg-white"
      :style="{ touchAction: 'none', cursor: isPanning ? 'grabbing' : 'grab' }"
      @wheel="onCanvasWheel"
      @pointerdown="onCanvasPointerDown"
      @pointermove="onCanvasPointerMove"
      @pointerup="onCanvasPointerUp"
      @pointercancel="onCanvasPointerUp"
    />

    <div class="px-4 py-2">
      <div class="h-1.5 w-full overflow-hidden rounded bg-slate-700">
        <div class="h-full bg-emerald-500" :style="{ width: `${progress * 100}%` }" />
      </div>
    </div>

    <dl class="grid grid-cols-2 gap-x-4 gap-y-1 px-4 pb-3 text-sm text-slate-300 sm:grid-cols-4">
      <div>
        <dt class="text-xs text-slate-500">{{ t('simulator.drawing') }}</dt>
        <dd class="font-mono">{{ formatDuration(sim.drawingTimeSeconds) }}</dd>
      </div>
      <div>
        <dt class="text-xs text-slate-500">{{ t('simulator.travel') }}</dt>
        <dd class="font-mono">{{ formatDuration(sim.travelTimeSeconds) }}</dd>
      </div>
      <div>
        <dt class="text-xs text-slate-500">{{ t('simulator.totalSim') }}</dt>
        <dd class="font-mono text-emerald-300">{{ formatDuration(sim.totalTimeSeconds) }}</dd>
      </div>
      <div>
        <dt class="text-xs text-slate-500">{{ t('simulator.layerEstimate') }}</dt>
        <dd class="font-mono">{{ formatDuration(store.totalDurationSeconds) }}</dd>
      </div>
      <div v-if="drawingSize">
        <dt class="text-xs text-slate-500">{{ t('simulator.dimensions') }}</dt>
        <dd class="font-mono">{{ drawingSize.w.toFixed(0) }}×{{ drawingSize.h.toFixed(0) }} mm</dd>
      </div>
    </dl>
  </section>
</template>
