<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'
import { useQueueStore } from '../stores/queue'
import { useUiStore } from '../stores/ui'
import AssistantModeToggle from './AssistantModeToggle.vue'

const { t } = useI18n()
const ui = useUiStore()
const plotter = usePlotterStore()
const queue = useQueueStore()
const job = useJobStore()
const { status: plotterStatus } = storeToRefs(plotter)

// Header transport controls: prefer the queued active run when one is
// live so the buttons drive the canonical queue lifecycle. Fall back
// to the direct serial state for one-shot ``plotter.run`` sends made
// from the drawer.
const activeRun = computed(() => queue.active[0] ?? null)
const runState = computed<'running' | 'paused' | 'idle'>(() => {
  const run = activeRun.value
  if (run) {
    if (run.state === 'running') return 'running'
    if (run.state === 'paused') return 'paused'
  }
  if (plotterStatus.value.state === 'running') return 'running'
  if (plotterStatus.value.state === 'paused') return 'paused'
  return 'idle'
})
const canPlay = computed(
  () =>
    runState.value === 'paused' ||
    (runState.value === 'idle' && plotterStatus.value.connected && Boolean(job.gcode)),
)
const canStop = computed(() => runState.value === 'running' || runState.value === 'paused')
const playTitle = computed(() =>
  runState.value === 'paused' ? t('plotter.resume') : t('plotter.sendJob'),
)

async function onPlay(): Promise<void> {
  if (runState.value === 'paused') {
    const run = activeRun.value
    if (run) {
      await queue.act(run.id, 'resume')
    } else {
      await plotter.resume()
    }
    return
  }
  if (!job.gcode) return
  const confirmed = await confirmAction({
    title: t('confirm.sendJobTitle'),
    message: t('confirm.sendJobMsg'),
    confirmLabel: t('plotter.sendJob'),
    cancelLabel: t('confirm.cancel'),
  })
  if (confirmed) await plotter.run(job.gcode)
}

async function onPause(): Promise<void> {
  const run = activeRun.value
  if (run) {
    await queue.act(run.id, 'pause')
  } else {
    await plotter.pause()
  }
}

async function onStop(): Promise<void> {
  const run = activeRun.value
  const confirmed = await confirmAction({
    title: t('plotter.stopTitle'),
    message: t('plotter.stopMsg'),
    confirmLabel: t('plotter.abort'),
    cancelLabel: t('confirm.cancel'),
    danger: true,
  })
  if (!confirmed) return
  if (run) {
    await queue.act(run.id, 'cancel')
  } else {
    await plotter.abort()
  }
}
</script>

<template>
  <header
    class="grid grid-cols-[1fr_auto_1fr] items-center gap-3 border-b border-slate-800 bg-slate-900/95 px-4 py-2 backdrop-blur"
  >
    <!-- LEFT zone: app brand. -->
    <div class="flex items-baseline justify-self-start gap-2">
      <h1 class="text-lg font-bold tracking-tight">OmniPlot</h1>
      <span
        class="rounded bg-sky-900/60 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-sky-300"
        data-test="header-version-badge"
        title="v0.2 wired"
      >
        v0.2
      </span>
    </div>

    <!-- CENTER zone: transport controls (play / pause / stop). Drive the
         active queued run when one is live, otherwise send the currently
         loaded gcode directly. Always visible — the play button is greyed
         out until a plotter is connected and a job is loaded. -->
    <div class="flex items-center justify-self-center">
      <div
        class="flex items-center gap-1 rounded border border-slate-700 bg-slate-800 p-0.5"
        data-test="header-transport"
      >
        <button
          v-if="runState !== 'running'"
          type="button"
          class="flex items-center gap-1 rounded px-2 py-1 text-xs text-emerald-300 hover:bg-emerald-900/40 disabled:opacity-40"
          :disabled="!canPlay"
          :title="playTitle"
          :aria-label="playTitle"
          data-test="header-play"
          @click="onPlay"
        >
          <span aria-hidden="true">▶</span>
          <span class="hidden md:inline">{{
            runState === 'paused' ? t('plotter.resume') : t('plotter.play')
          }}</span>
        </button>
        <button
          v-else
          type="button"
          class="flex items-center gap-1 rounded px-2 py-1 text-xs text-amber-300 hover:bg-amber-900/40"
          :title="t('plotter.pause')"
          :aria-label="t('plotter.pause')"
          data-test="header-pause"
          @click="onPause"
        >
          <span aria-hidden="true">‖</span>
          <span class="hidden md:inline">{{ t('plotter.pause') }}</span>
        </button>
        <button
          type="button"
          class="flex items-center gap-1 rounded px-2 py-1 text-xs text-red-300 hover:bg-red-900/40 disabled:opacity-40"
          :disabled="!canStop"
          :title="t('plotter.abort')"
          :aria-label="t('plotter.abort')"
          data-test="header-stop"
          @click="onStop"
        >
          <span aria-hidden="true">■</span>
          <span class="hidden md:inline">{{ t('plotter.stop') }}</span>
        </button>
      </div>
    </div>

    <!-- RIGHT zone: mode toggle + plotter settings + app settings. -->
    <div class="flex items-center justify-self-end gap-3">
      <!-- AssistantModeToggle is the single mode selector (Assisté /
           Expert). The legacy ``Débutant / Pro`` workspace switcher
           was removed in 2026-05-28 — it shared a header slot with
           this toggle and the two distinct concepts (skill level vs
           layout preset) were indistinguishable in the field. The
           workspace store still exists for future use but no longer
           has a UI surface. -->
      <AssistantModeToggle data-test="header-assistant-mode-toggle" />

      <!-- Plotter access: opens the plotter settings modal (connection,
           profile, colours, macros, queue). The coloured dot mirrors the
           connection state — green when the traceur is linked, grey
           otherwise — so the entry point doubles as a status indicator
           without hiding what the button actually does. -->
      <button
        type="button"
        class="flex items-center gap-2 rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700"
        :title="t('plotter.settingsTitle')"
        :aria-label="t('plotter.settingsTitle')"
        data-test="header-plotter"
        @click="ui.openPlotterSettings()"
      >
        <span
          class="h-2 w-2 rounded-full"
          :class="plotterStatus.connected ? 'bg-emerald-400' : 'bg-slate-500'"
          :aria-label="
            plotterStatus.connected ? t('plotter.connected') : t('machine.disconnected')
          "
        />
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="h-4 w-4"
        >
          <path
            d="M14.7 6.3a4 4 0 0 0-5.4 5.4l-6 6a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l6-6a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.5-2.5z"
          />
        </svg>
        <span class="hidden sm:inline">{{ t('plotter.settingsTitle') }}</span>
      </button>

      <button
        type="button"
        class="flex items-center gap-1.5 rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700"
        :title="t('header.settings')"
        :aria-label="t('header.settings')"
        @click="ui.openSettings()"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="h-4 w-4"
        >
          <circle cx="12" cy="12" r="3" />
          <path
            d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
          />
        </svg>
        <span class="hidden sm:inline">{{ t('header.settings') }}</span>
      </button>
    </div>
  </header>
</template>
