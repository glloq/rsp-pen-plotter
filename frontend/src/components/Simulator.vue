<script setup lang="ts">
// Simulator orchestrator (L10 #1 finalize).
//
// Post-split this component is a thin wiring layer:
//   - drives ``useGcodePlayback`` with the job store's gcode +
//     selected profile
//   - owns the cross-slice state that the composable doesn't:
//     viewport (zoom/pan) + display toggles + colour filter
//   - handles store side-effects (``manualPenChange`` mutates layers
//     across placements; ``ui.canvasTab`` watch jumps to the end
//     when the operator enters the tab)
//   - renders the progress bar + stats footer
//
// Heavy lifting lives in three siblings:
//   - ``useGcodePlayback`` — play / pause / seek / RAF loop
//   - ``<SimControls>``    — toolbar buttons + colour chips
//   - ``<SimCanvas>``      — 2D drawing of segments + markers

import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'
import { type SimBounds } from '../lib/gcode'
import { useGcodePlayback } from '../composables/useGcodePlayback'
import SimCanvas from './SimCanvas.vue'
import SimControls from './SimControls.vue'

const { t } = useI18n()
const store = useJobStore()
const ui = useUiStore()
const { gcode } = storeToRefs(store)

// Parse options derive from the selected machine profile. The
// composable subscribes to this ref, so swapping profiles
// re-runs ``parseGcode`` with the new pen-up / pen-down / speed
// settings — no manual call needed here.
const parseOptions = computed(() => {
  const profile = store.selectedProfile
  if (!profile) return null
  return {
    penUpCommand: profile.pen_up_command,
    penDownCommand: profile.pen_down_command,
    travelSpeedMmS: profile.travel_speed_mm_s,
    defaultDrawSpeedMmS: profile.drawing_speed_mm_s,
    toolChangeCommand: profile.tool_change_command,
  }
})

const { sim, playing, simTime, speed, play, pause, restart, jumpToEnd } = useGcodePlayback({
  gcode,
  parseOptions,
})

// ---- Viewport (zoom/pan) ------------------------------------------------
// Lives here rather than inside ``<SimCanvas>`` because ``resetView``
// reads store data (profile.origin) AND sim bounds, and the SimControls'
// zoom-percentage display has to mirror the same number. Both
// sub-components receive it as a prop and emit ``update:`` events.

const viewZoom = ref(1)
const viewPanX = ref(0)
const viewPanY = ref(0)

const WIDTH = 800
const HEIGHT = 420
const PAD = 20

const frameBounds = computed<SimBounds>(() => {
  const ws = store.selectedProfile?.workspace
  if (ws && ws.x_max > ws.x_min && ws.y_max > ws.y_min) {
    return { minX: ws.x_min, minY: ws.y_min, maxX: ws.x_max, maxY: ws.y_max }
  }
  return sim.value?.bounds ?? { minX: 0, minY: 0, maxX: 1, maxY: 1 }
})

const flipOriginY = computed(() => store.selectedProfile?.origin !== 'top_left')

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
    return
  }
  // ``project()`` in SimCanvas scales workspace units to the canvas;
  // ``viewZoom`` multiplies that. To make the drawing fill ~80 % of
  // the canvas we need (fillRatio * frame / drawing), clamped to the
  // manual zoom limits so very tiny drawings don't disappear past the
  // upper bound.
  const fillRatio = 0.8
  const zoom = Math.max(1, Math.min(12, Math.min((fw * fillRatio) / bw, (fh * fillRatio) / bh)))
  viewZoom.value = zoom
  // Now pan so the drawing's centre lands on the canvas centre. We
  // re-derive the same base scale ``project`` uses (note: NOT the
  // post-zoom scale) and undo the offset that would otherwise leave
  // the drawing where the workspace centre projects to.
  const base = Math.min((WIDTH - 2 * PAD) / fw, (HEIGHT - 2 * PAD) / fh)
  const flip = flipOriginY.value
  const bcx = (s!.bounds.minX + s!.bounds.maxX) / 2
  const bcy = (s!.bounds.minY + s!.bounds.maxY) / 2
  const cxCanvas = PAD + (bcx - f.minX) * base
  const cyCanvas = flip ? PAD + (f.maxY - bcy) * base : PAD + (bcy - f.minY) * base
  viewPanX.value = -(cxCanvas - WIDTH / 2) * zoom
  viewPanY.value = -(cyCanvas - HEIGHT / 2) * zoom
}

function zoomIn(): void {
  viewZoom.value = Math.min(viewZoom.value * 1.25, 12)
}

function zoomOut(): void {
  viewZoom.value = Math.max(viewZoom.value / 1.25, 0.2)
}

// Auto-fit on every (re)parse: ``useGcodePlayback`` swaps the ``sim``
// ref when the source or profile changes, so we react to that. The
// initial mount lands a ``sim`` value (via the composable's immediate
// watch), which fires this handler exactly once with the fresh data.
watch(sim, () => resetView())

// When the operator switches into the simulator tab, jump straight to
// the end of the plot and recentre on the workspace — the default view
// shows the finished drawing, not an empty canvas.
watch(
  () => ui.canvasTab,
  (tab) => {
    if (tab !== 'simulator' || !sim.value) return
    pause()
    jumpToEnd()
    resetView()
  },
)

// ---- Display toggles + colour filter -----------------------------------
// Each toggle scopes a different piece of information the operator
// might want to inspect on the preview. They all default to "show" so
// the initial view matches the previous behaviour (drawing + travel
// + pen). ``colorFilter`` stores the set of HEX strings to draw; an
// empty filter means "draw all colours" (treated as a wildcard so the
// operator doesn't stare at a blank canvas when no tool-change
// markers were emitted).
const showTravel = ref(true)
const showPenEvents = ref(false)
const showColorChanges = ref(true)
const showPauses = ref(true)
const colorFilter = ref<Set<string>>(new Set())

// Reset the colour filter whenever a fresh plot lands so chips for
// the previous plot's colours don't hide every segment of the new
// one.
watch(sim, () => {
  colorFilter.value = new Set()
})

function toggleColor(hex: string): void {
  const next = new Set(colorFilter.value)
  if (next.has(hex)) next.delete(hex)
  else next.add(hex)
  colorFilter.value = next
}

function selectAllColors(): void {
  colorFilter.value = new Set()
}

function selectOnlyColor(hex: string): void {
  colorFilter.value = new Set([hex])
}

// ---- Manual pen change --------------------------------------------------
// Only relevant on single-pen machines. When enabled, every layer is
// marked ``pause_before='always'`` so the operator gets prompted
// before each colour transition. This crosses the placement boundary
// (mutates every layer of every placement) and stays in the
// orchestrator because the sub-components are presentational.
const isMultiColor = computed(() => store.isMultiColor)
// Use visiblePlacements — Edit-from-library drafts hold layers but
// aren't on the sheet, so they shouldn't count for simulator stats
// or the pen-change toggle (audit 2026-05-27).
const allLayers = computed(() => store.visiblePlacements.flatMap((p) => p.layers))
const manualPenChange = computed<boolean>({
  get: () =>
    allLayers.value.length > 0 && allLayers.value.every((l) => l.pause_before === 'always'),
  set: (value) => {
    const target = value ? 'always' : 'auto'
    const prev = store.selectedPlacementId
    for (const placement of store.visiblePlacements) {
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

// ---- Stats footer -------------------------------------------------------
const drawingSize = computed(() => {
  const b = sim.value?.bounds
  if (!b || b.maxX < b.minX) return null
  return { w: b.maxX - b.minX, h: b.maxY - b.minY }
})

const progress = computed(() =>
  sim.value && sim.value.totalTimeSeconds > 0 ? simTime.value / sim.value.totalTimeSeconds : 0,
)

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs.toString().padStart(2, '0')}s`
}

// SimControls emits intent events. Most pass straight through to the
// composable / view-state mutators; a couple need a tiny bit of glue
// (play vs. toggle, manualPenChange's setter).
function onUpdateManualPenChange(value: boolean): void {
  manualPenChange.value = value
}
</script>

<template>
  <section
    v-if="sim"
    class="flex h-full min-h-0 flex-col rounded-lg border border-slate-700 bg-slate-800/60"
  >
    <SimControls
      :playing="playing"
      :speed="speed"
      :view-zoom="viewZoom"
      :show-travel="showTravel"
      :show-pen-events="showPenEvents"
      :show-color-changes="showColorChanges"
      :show-pauses="showPauses"
      :is-multi-color="isMultiColor"
      :manual-pen-change="manualPenChange"
      :colors="sim.colors"
      :color-filter="colorFilter"
      @play="play"
      @pause="pause"
      @restart="restart"
      @jump-to-end="jumpToEnd"
      @update:speed="(v) => (speed = v)"
      @zoom-in="zoomIn"
      @zoom-out="zoomOut"
      @reset-view="resetView"
      @update:show-travel="(v) => (showTravel = v)"
      @update:show-pen-events="(v) => (showPenEvents = v)"
      @update:show-color-changes="(v) => (showColorChanges = v)"
      @update:show-pauses="(v) => (showPauses = v)"
      @update:manual-pen-change="onUpdateManualPenChange"
      @toggle-color="toggleColor"
      @select-all-colors="selectAllColors"
      @select-only-color="selectOnlyColor"
    />

    <SimCanvas
      :sim="sim"
      :sim-time="simTime"
      :frame-bounds="frameBounds"
      :flip-origin-y="flipOriginY"
      :view-zoom="viewZoom"
      :view-pan-x="viewPanX"
      :view-pan-y="viewPanY"
      :show-travel="showTravel"
      :show-pen-events="showPenEvents"
      :show-color-changes="showColorChanges"
      :show-pauses="showPauses"
      :color-filter="colorFilter"
      @update:view-zoom="(v) => (viewZoom = v)"
      @update:view-pan-x="(v) => (viewPanX = v)"
      @update:view-pan-y="(v) => (viewPanY = v)"
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
