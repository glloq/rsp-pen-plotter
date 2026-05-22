<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useJobStore } from '../stores/job'
import { parseGcode, type SimBounds, type SimResult } from '../lib/gcode'

const store = useJobStore()
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
  return [cx, cy]
}

function draw(): void {
  const c = canvas.value
  const r = sim.value
  if (!c || !r) return
  const ctx = c.getContext('2d')
  if (!ctx) return

  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, WIDTH, HEIGHT)
  const t = simTime.value
  let pen: [number, number] | null = null

  for (const seg of r.segments) {
    if (seg.startTime >= t) break
    const frac = seg.duration > 0 ? Math.min(1, (t - seg.startTime) / seg.duration) : 1
    const ex = seg.x0 + (seg.x1 - seg.x0) * frac
    const ey = seg.y0 + (seg.y1 - seg.y0) * frac
    const [ax, ay] = project(seg.x0, seg.y0, r.bounds)
    const [bx, by] = project(ex, ey, r.bounds)
    ctx.beginPath()
    ctx.moveTo(ax, ay)
    ctx.lineTo(bx, by)
    if (seg.drawing) {
      ctx.strokeStyle = '#0f172a'
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

  if (pen) {
    ctx.beginPath()
    ctx.arc(pen[0], pen[1], 3, 0, Math.PI * 2)
    ctx.fillStyle = '#10b981'
    ctx.fill()
  }
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
  })
  simTime.value = 0
  draw()
}

watch(gcode, () => reparse())
onMounted(() => reparse())
onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <section v-if="sim" class="mt-4 rounded-lg border border-slate-700 bg-slate-800">
    <div class="flex flex-wrap items-center gap-2 border-b border-slate-700 px-4 py-2">
      <h2 class="mr-auto text-sm uppercase tracking-wide text-slate-400">Simulator</h2>
      <button
        type="button"
        class="rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-1 text-sm text-white"
        @click="playing ? pause() : play()"
      >
        {{ playing ? 'Pause' : 'Play' }}
      </button>
      <button
        type="button"
        class="rounded bg-slate-700 hover:bg-slate-600 px-3 py-1 text-sm text-slate-100"
        @click="restart"
      >
        Restart
      </button>
      <button
        v-for="s in speeds"
        :key="s"
        type="button"
        class="rounded px-2 py-1 text-sm"
        :class="speed === s ? 'bg-sky-600 text-white' : 'bg-slate-700 text-slate-200'"
        @click="speed = s"
      >
        {{ s }}×
      </button>
      <button
        type="button"
        class="rounded bg-slate-700 hover:bg-slate-600 px-2 py-1 text-sm text-slate-100"
        @click="jumpToEnd"
      >
        max
      </button>
    </div>

    <canvas ref="canvas" :width="WIDTH" :height="HEIGHT" class="w-full bg-white" />

    <div class="px-4 py-2">
      <div class="h-1.5 w-full overflow-hidden rounded bg-slate-700">
        <div class="h-full bg-emerald-500" :style="{ width: `${progress * 100}%` }" />
      </div>
    </div>

    <dl class="grid grid-cols-2 gap-x-4 gap-y-1 px-4 pb-3 text-sm text-slate-300 sm:grid-cols-4">
      <div>
        <dt class="text-xs text-slate-500">Drawing</dt>
        <dd class="font-mono">{{ formatDuration(sim.drawingTimeSeconds) }}</dd>
      </div>
      <div>
        <dt class="text-xs text-slate-500">Travel</dt>
        <dd class="font-mono">{{ formatDuration(sim.travelTimeSeconds) }}</dd>
      </div>
      <div>
        <dt class="text-xs text-slate-500">Total (sim)</dt>
        <dd class="font-mono text-emerald-300">{{ formatDuration(sim.totalTimeSeconds) }}</dd>
      </div>
      <div>
        <dt class="text-xs text-slate-500">Layer estimate</dt>
        <dd class="font-mono">{{ formatDuration(store.totalDurationSeconds) }}</dd>
      </div>
    </dl>
  </section>
</template>
