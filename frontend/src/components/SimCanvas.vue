<script setup lang="ts">
// Canvas renderer for the Simulator (L10 #1 extract).
//
// Owns the 2D drawing surface and the imperative ``draw()`` loop. The
// orchestrator passes in the playback state (``sim``, ``simTime``)
// plus display toggles + viewport transform; this component watches
// those props and re-renders on every change. Interactive wheel /
// pointer events are translated into ``update:viewZoom`` /
// ``update:viewPanX`` / ``update:viewPanY`` emits so the orchestrator
// remains the single source of truth for viewport state (which it
// shares with the SimControls' zoom percentage display + the
// auto-fit ``resetView`` logic that depends on store data).
//
// Why imperative canvas instead of declarative SVG: G-code plots can
// have tens of thousands of segments, and re-rendering them through
// Vue's reconciler on every ``simTime`` tick was the original
// performance bottleneck on the Pi. The 2D context lets us batch
// segments per stroke style and walk them in a single pass.

import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { SimBounds, SimResult } from '../lib/gcode'

const props = defineProps<{
  sim: SimResult | null
  simTime: number
  frameBounds: SimBounds
  /** Whether the source profile uses a bottom-origin (most CNC
   *  controllers) or a top-origin (e.g. some plotters). Used to flip
   *  the Y axis when projecting world coordinates. */
  flipOriginY: boolean
  viewZoom: number
  viewPanX: number
  viewPanY: number
  showTravel: boolean
  showPenEvents: boolean
  showColorChanges: boolean
  showPauses: boolean
  /** Pen-up heatmap (v2 P7): colour travel moves by their length so
   *  wasteful hops jump out — short hops stay amber, the longest
   *  travels burn red and thick. Replaces the plain dashed sky style
   *  while active (implies travel visibility for the heat to read). */
  showPenupHeat: boolean
  /** Path-density underlay (v2 P7): accumulate drawing segments as
   *  thick low-alpha strokes below the plot so over-inked zones
   *  (multiple passes, dense hatching) darken visibly. */
  showDensity: boolean
  colorFilter: Set<string>
}>()

const emit = defineEmits<{
  'update:viewZoom': [value: number]
  'update:viewPanX': [value: number]
  'update:viewPanY': [value: number]
}>()

defineExpose({
  draw: () => draw(),
})

// Canvas dimensions are fixed in CSS pixels; ``draw()`` upgrades the
// backing store to devicePixelRatio so HiDPI displays stay crisp.
const WIDTH = 800
const HEIGHT = 420
const PAD = 20

const canvas = ref<HTMLCanvasElement | null>(null)
const isPanning = ref(false)
let panStartX = 0
let panStartY = 0
let panOriginX = 0
let panOriginY = 0

function isColorVisible(hex: string | null): boolean {
  if (props.colorFilter.size === 0) return true
  // Segments emitted before any tool_change marker have ``null`` as
  // their colour. Keep them visible whenever the filter contains a
  // sentinel empty string or matches the actual hex.
  return props.colorFilter.has(hex ?? '')
}

// Fit-scale (world mm → canvas px) for the given bounds. Hoisted out of
// ``project`` so ``draw`` computes it ONCE per frame instead of twice per
// segment (tens of thousands of redundant min/div ops per frame on a dense
// plot — the per-point recompute the audit flagged).
function fitScale(b: SimBounds): number {
  return Math.min(
    (WIDTH - 2 * PAD) / Math.max(b.maxX - b.minX, 1e-6),
    (HEIGHT - 2 * PAD) / Math.max(b.maxY - b.minY, 1e-6),
  )
}

function project(x: number, y: number, b: SimBounds, s: number): [number, number] {
  const cx = PAD + (x - b.minX) * s
  const cy = props.flipOriginY ? PAD + (b.maxY - y) * s : PAD + (y - b.minY) * s
  // Apply view transform: zoom around the canvas centre, then translate.
  const zx = (cx - WIDTH / 2) * props.viewZoom + WIDTH / 2 + props.viewPanX
  const zy = (cy - HEIGHT / 2) * props.viewZoom + HEIGHT / 2 + props.viewPanY
  return [zx, zy]
}

// Longest travel move in the sim (world units), cached per SimResult —
// the heat scale needs it every frame and the segment list can be tens
// of thousands long.
let heatSim: SimResult | null = null
let heatMax = 0

function maxTravelLength(r: SimResult): number {
  if (heatSim !== r) {
    heatSim = r
    heatMax = 0
    for (const seg of r.segments) {
      if (seg.drawing) continue
      const len = Math.hypot(seg.x1 - seg.x0, seg.y1 - seg.y0)
      if (len > heatMax) heatMax = len
    }
  }
  return heatMax
}

function draw(): void {
  const c = canvas.value
  const r = props.sim
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

  const bounds = props.frameBounds
  const s = fitScale(bounds)
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, WIDTH, HEIGHT)

  // Sheet / workspace outline.
  const [sx0, sy0] = project(bounds.minX, bounds.minY, bounds, s)
  const [sx1, sy1] = project(bounds.maxX, bounds.maxY, bounds, s)
  ctx.strokeStyle = '#94a3b8'
  ctx.lineWidth = 1
  ctx.setLineDash([])
  ctx.strokeRect(Math.min(sx0, sx1), Math.min(sy0, sy1), Math.abs(sx1 - sx0), Math.abs(sy1 - sy0))

  const t = props.simTime
  let pen: [number, number] | null = null

  // Density underlay: aggregate pass below the plot. Full segments only
  // (no partial-frac interpolation) — this is a heat aggregate, not the
  // playback head.
  if (props.showDensity) {
    ctx.save()
    ctx.strokeStyle = 'rgba(124, 58, 237, 0.07)'
    ctx.lineWidth = 6
    ctx.lineCap = 'round'
    for (const seg of r.segments) {
      if (seg.startTime >= t) break
      if (!seg.drawing || !isColorVisible(seg.colorHex)) continue
      const [ax, ay] = project(seg.x0, seg.y0, bounds, s)
      const [bx, by] = project(seg.x1, seg.y1, bounds, s)
      ctx.beginPath()
      ctx.moveTo(ax, ay)
      ctx.lineTo(bx, by)
      ctx.stroke()
    }
    ctx.restore()
  }

  const heatMaxLen = props.showPenupHeat ? maxTravelLength(r) : 0

  for (const seg of r.segments) {
    if (seg.startTime >= t) break
    // Apply the colour filter — only to drawing segments; travel moves
    // inherit visibility from ``showTravel`` instead because they have
    // no inherent colour.
    if (seg.drawing && !isColorVisible(seg.colorHex)) {
      pen = project(seg.x1, seg.y1, bounds, s)
      continue
    }
    if (!seg.drawing && !props.showTravel && !props.showPenupHeat) {
      pen = project(seg.x1, seg.y1, bounds, s)
      continue
    }
    const frac = seg.duration > 0 ? Math.min(1, (t - seg.startTime) / seg.duration) : 1
    const ex = seg.x0 + (seg.x1 - seg.x0) * frac
    const ey = seg.y0 + (seg.y1 - seg.y0) * frac
    const [ax, ay] = project(seg.x0, seg.y0, bounds, s)
    const [bx, by] = project(ex, ey, bounds, s)
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
    } else if (props.showPenupHeat) {
      // Heat scale: hue slides amber (48°) → red (0°) and the stroke
      // thickens with the travel's share of the longest hop, so the
      // most wasteful moves dominate the view.
      const len = Math.hypot(seg.x1 - seg.x0, seg.y1 - seg.y0)
      const heat = heatMaxLen > 0 ? Math.min(1, len / heatMaxLen) : 0
      ctx.strokeStyle = `hsl(${Math.round(48 - 48 * heat)} 95% ${Math.round(58 - 13 * heat)}%)`
      ctx.lineWidth = 0.8 + 1.8 * heat
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
    const [ex, ey] = project(ev.x, ev.y, bounds, s)
    if (ev.type === 'pen_up' || ev.type === 'pen_down') {
      if (!props.showPenEvents) continue
      drawPenEventMarker(ctx, ex, ey, ev.type === 'pen_up')
    } else if (ev.type === 'tool_change') {
      if (!props.showColorChanges) continue
      drawToolChangeMarker(ctx, ex, ey, ev.colorHex || '#f59e0b')
    } else if (ev.type === 'pause') {
      if (!props.showPauses) continue
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

function onCanvasWheel(event: WheelEvent): void {
  event.preventDefault()
  const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15
  emit('update:viewZoom', Math.max(0.2, Math.min(props.viewZoom * factor, 12)))
}

function onCanvasPointerDown(event: PointerEvent): void {
  if (event.button !== 0 && event.button !== 1) return
  isPanning.value = true
  panStartX = event.clientX
  panStartY = event.clientY
  panOriginX = props.viewPanX
  panOriginY = props.viewPanY
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

// Each pan emit updates a viewport prop → triggers a full O(segments)
// canvas redraw. Coalesce the high-frequency pointer events to one emit
// per animation frame so panning a large plot stays smooth.
let panClientX = 0
let panClientY = 0
let panRaf = 0

function flushPan(): void {
  panRaf = 0
  emit('update:viewPanX', panOriginX + (panClientX - panStartX))
  emit('update:viewPanY', panOriginY + (panClientY - panStartY))
}

function onCanvasPointerMove(event: PointerEvent): void {
  if (!isPanning.value) return
  panClientX = event.clientX
  panClientY = event.clientY
  if (panRaf === 0) panRaf = requestAnimationFrame(flushPan)
}

function onCanvasPointerUp(event: PointerEvent): void {
  isPanning.value = false
  if (panRaf !== 0) {
    cancelAnimationFrame(panRaf)
    flushPan()
  }
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
}

onBeforeUnmount(() => {
  if (panRaf !== 0) cancelAnimationFrame(panRaf)
})

// Watch every prop the renderer reads so the canvas re-paints on
// state changes (simTime ticks, display toggles flipping, viewport
// transforms, filter mutations). The Simulator's RAF loop drives
// ``simTime``, which lands here as a prop update.
watch(
  () => [
    props.sim,
    props.simTime,
    props.frameBounds,
    props.viewZoom,
    props.viewPanX,
    props.viewPanY,
    props.showTravel,
    props.showPenEvents,
    props.showColorChanges,
    props.showPauses,
    props.showPenupHeat,
    props.showDensity,
    props.colorFilter,
  ],
  () => draw(),
)

onMounted(() => draw())
</script>

<template>
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
</template>
