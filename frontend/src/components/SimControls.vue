<script setup lang="ts">
// Toolbar for the Simulator (L10 #1 extract).
//
// Pure presentational component: every button emits an event the
// orchestrator translates into a composable / state mutation. The
// only locally-derived state is the i18n labels and the active-
// highlight classes that flip with the boolean props.
//
// Two prop families:
//   - playback state (``playing``, ``speed``, ``viewZoom``): mirror
//     the composable so the right label / active class shows.
//   - display toggles + colour filter: live in the Simulator
//     orchestrator (they're rendering concerns shared with
//     ``<SimCanvas>``); SimControls receives them as v-model props
//     and emits ``update:`` events.

import { useI18n } from 'vue-i18n'
import type { SimColor } from '../lib/gcode'

const { t } = useI18n()

defineProps<{
  playing: boolean
  speed: number
  viewZoom: number
  showTravel: boolean
  showPenEvents: boolean
  showColorChanges: boolean
  showPauses: boolean
  showPenupHeat: boolean
  showDensity: boolean
  isMultiColor: boolean
  manualPenChange: boolean
  colors: SimColor[]
  colorFilter: Set<string>
}>()

const emit = defineEmits<{
  play: []
  pause: []
  restart: []
  jumpToEnd: []
  'update:speed': [value: number]
  zoomIn: []
  zoomOut: []
  resetView: []
  'update:showTravel': [value: boolean]
  'update:showPenEvents': [value: boolean]
  'update:showColorChanges': [value: boolean]
  'update:showPauses': [value: boolean]
  'update:showPenupHeat': [value: boolean]
  'update:showDensity': [value: boolean]
  'update:manualPenChange': [value: boolean]
  toggleColor: [hex: string]
  selectAllColors: []
  selectOnlyColor: [hex: string]
}>()

// Preset row of speed multipliers — three discrete buttons rather
// than a slider keeps the toolbar legible on narrow viewports and
// matches the pre-split UX exactly.
const speeds = [1, 5, 100]

function onTogglePlayback(playing: boolean): void {
  // Discrete branches keep ``defineEmits``'s discriminated union
  // happy; a single ternary call confuses the inferred overload.
  if (playing) emit('pause')
  else emit('play')
}
</script>

<template>
  <div>
    <!-- Single compact toolbar — playback, zoom and display toggles
         all live on the same row. The zoom group is rendered with a
         heavier border + larger glyphs so it remains the most visually
         obvious control cluster (operators reach for it constantly
         during scrub playback). Display toggles are pill buttons that
         highlight when active, which fits more controls in less
         vertical space than a checkbox grid did. -->
    <div class="flex flex-wrap items-center gap-1.5 border-b border-slate-700 px-3 py-1.5 text-xs">
      <button
        type="button"
        class="rounded bg-emerald-600 hover:bg-emerald-500 px-2.5 py-1 font-medium text-white"
        @click="onTogglePlayback(playing)"
      >
        {{ playing ? t('simulator.pause') : t('simulator.play') }}
      </button>
      <button
        type="button"
        class="rounded bg-slate-700 hover:bg-slate-600 px-2 py-1 text-slate-100"
        :title="t('simulator.restart')"
        @click="emit('restart')"
      >
        ⟲
      </button>
      <button
        v-for="s in speeds"
        :key="s"
        type="button"
        class="rounded px-1.5 py-1 font-mono"
        :class="
          speed === s ? 'bg-sky-600 text-white' : 'bg-slate-700 text-slate-200 hover:bg-slate-600'
        "
        @click="emit('update:speed', s)"
      >
        {{ s }}×
      </button>
      <button
        type="button"
        class="rounded bg-slate-700 hover:bg-slate-600 px-2 py-1 text-slate-100"
        :title="t('simulator.end')"
        @click="emit('jumpToEnd')"
      >
        ⏭
      </button>

      <!-- Zoom cluster — boxed, bold, slightly taller than its neighbours. -->
      <div
        class="ml-1 flex items-center gap-0.5 rounded-md border border-sky-700/70 bg-slate-900 px-0.5 py-0.5 shadow-sm"
      >
        <button
          type="button"
          class="rounded px-2 py-0.5 text-base font-bold text-sky-200 hover:bg-slate-800"
          :title="t('simulator.zoomOut')"
          @click="emit('zoomOut')"
        >
          −
        </button>
        <span class="w-11 text-center font-mono text-[11px] text-slate-300"
          >{{ Math.round(viewZoom * 100) }}%</span
        >
        <button
          type="button"
          class="rounded px-2 py-0.5 text-base font-bold text-sky-200 hover:bg-slate-800"
          :title="t('simulator.zoomIn')"
          @click="emit('zoomIn')"
        >
          +
        </button>
        <button
          type="button"
          class="rounded px-1.5 py-0.5 text-slate-200 hover:bg-slate-800"
          :title="t('simulator.resetView')"
          @click="emit('resetView')"
        >
          ⤢
        </button>
      </div>

      <!-- Display toggles as pill buttons. Each pill highlights with a
           colour that matches its marker glyph on the canvas so the
           legend is implicit (travel = sky, pen events = amber, etc.). -->
      <button
        type="button"
        class="rounded border px-1.5 py-1"
        :class="
          showTravel
            ? 'border-sky-500 bg-sky-600/30 text-sky-100'
            : 'border-slate-700 bg-slate-900 text-slate-400 hover:bg-slate-800'
        "
        :title="t('simulator.optTravel')"
        @click="emit('update:showTravel', !showTravel)"
      >
        ⤳
      </button>
      <button
        type="button"
        class="rounded border px-1.5 py-1"
        :class="
          showPenEvents
            ? 'border-amber-500 bg-amber-600/30 text-amber-100'
            : 'border-slate-700 bg-slate-900 text-slate-400 hover:bg-slate-800'
        "
        :title="t('simulator.optPenEvents')"
        @click="emit('update:showPenEvents', !showPenEvents)"
      >
        ▲▼
      </button>
      <button
        type="button"
        class="rounded border px-1.5 py-1"
        :class="
          showColorChanges
            ? 'border-emerald-500 bg-emerald-600/30 text-emerald-100'
            : 'border-slate-700 bg-slate-900 text-slate-400 hover:bg-slate-800'
        "
        :title="t('simulator.optColorChanges')"
        @click="emit('update:showColorChanges', !showColorChanges)"
      >
        ●
      </button>
      <button
        type="button"
        class="rounded border px-1.5 py-1"
        :class="
          showPenupHeat
            ? 'border-rose-500 bg-rose-600/30 text-rose-100'
            : 'border-slate-700 bg-slate-900 text-slate-400 hover:bg-slate-800'
        "
        :title="t('simulator.optPenupHeat')"
        data-test="sim-toggle-penup-heat"
        @click="emit('update:showPenupHeat', !showPenupHeat)"
      >
        🔥
      </button>
      <button
        type="button"
        class="rounded border px-1.5 py-1"
        :class="
          showDensity
            ? 'border-violet-500 bg-violet-600/30 text-violet-100'
            : 'border-slate-700 bg-slate-900 text-slate-400 hover:bg-slate-800'
        "
        :title="t('simulator.optDensity')"
        data-test="sim-toggle-density"
        @click="emit('update:showDensity', !showDensity)"
      >
        ▦
      </button>
      <button
        type="button"
        class="rounded border px-1.5 py-1"
        :class="
          showPauses
            ? 'border-amber-500 bg-amber-600/30 text-amber-100'
            : 'border-slate-700 bg-slate-900 text-slate-400 hover:bg-slate-800'
        "
        :title="t('simulator.optPauses')"
        @click="emit('update:showPauses', !showPauses)"
      >
        ❚❚
      </button>

      <label
        v-if="!isMultiColor"
        class="ml-auto flex items-center gap-1.5 text-slate-300"
        :title="t('simulator.manualPenChangeHint')"
      >
        <input
          type="checkbox"
          :checked="manualPenChange"
          class="h-3.5 w-3.5 accent-emerald-500"
          @change="(e) => emit('update:manualPenChange', (e.target as HTMLInputElement).checked)"
        />
        {{ t('simulator.manualPenChange') }}
      </label>
    </div>

    <div
      v-if="colors.length > 0"
      class="flex flex-wrap items-center gap-2 border-b border-slate-700 px-4 py-1.5 text-xs"
    >
      <span class="font-medium uppercase tracking-wide text-slate-500">
        {{ t('simulator.colors') }}
      </span>
      <button
        type="button"
        class="rounded border border-slate-700 px-2 py-0.5 text-slate-200 hover:bg-slate-800"
        :class="colorFilter.size === 0 ? 'bg-slate-700' : 'bg-slate-900'"
        @click="emit('selectAllColors')"
      >
        {{ t('simulator.colorAll') }}
      </button>
      <button
        v-for="c in colors"
        :key="c.hex || c.label"
        type="button"
        class="flex items-center gap-1.5 rounded border px-2 py-0.5"
        :class="
          colorFilter.size === 0 || colorFilter.has(c.hex)
            ? 'border-slate-500 bg-slate-700 text-slate-100'
            : 'border-slate-700 bg-slate-900 text-slate-400'
        "
        :title="`${c.label || c.hex || '—'} — ${t('simulator.colorClickHint')}`"
        @click="emit('toggleColor', c.hex)"
        @dblclick="emit('selectOnlyColor', c.hex)"
      >
        <span
          class="inline-block h-3 w-3 rounded-sm border border-slate-600"
          :style="{ backgroundColor: c.hex || '#94a3b8' }"
          aria-hidden="true"
        />
        <span class="text-slate-400">({{ c.segmentCount }})</span>
      </button>
    </div>
  </div>
</template>
