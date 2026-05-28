<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'
import { useQueueStore } from '../stores/queue'
import { useUiModeStore } from '../stores/uiMode'
import { useUiStore } from '../stores/ui'
import AssistantModeToggle from './AssistantModeToggle.vue'
import MachineStatusPill from './MachineStatusPill.vue'

const { t } = useI18n()
const ui = useUiStore()
const uiMode = useUiModeStore()
const plotter = usePlotterStore()
const queue = useQueueStore()
const job = useJobStore()
const { status: plotterStatus } = storeToRefs(plotter)

const workshopOn = computed(() => uiMode.isFlagEnabled('workshopMode'))

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

function toggleWorkshop(): void {
  uiMode.setFlag('workshopMode', !workshopOn.value)
}

// The legacy ``Modal V2 (beta)`` header toggle is gone: the
// ``AssistantModeToggle`` (Assisté / Expert) is now the single
// editor selector. Assisted opens the wizard, Expert opens the
// rich editor. See App.vue ``editorIsWizard`` for the wiring.
</script>

<template>
  <header
    class="flex flex-wrap items-center gap-3 border-b border-slate-800 bg-slate-900/95 px-4 py-2 backdrop-blur"
  >
    <div class="mr-2 flex items-baseline gap-2">
      <h1 class="text-lg font-bold tracking-tight">OmniPlot</h1>
      <span
        class="rounded bg-sky-900/60 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-sky-300"
        data-test="header-version-badge"
        title="v0.2 wired"
      >
        v0.2
      </span>
    </div>

    <div class="ml-auto flex items-center gap-3">
      <!-- AssistantModeToggle is the single mode selector (Assisté /
           Expert). The legacy ``Débutant / Pro`` workspace switcher
           was removed in 2026-05-28 — it shared a header slot with
           this toggle and the two distinct concepts (skill level vs
           layout preset) were indistinguishable in the field. The
           workspace store still exists for future use but no longer
           has a UI surface. -->
      <AssistantModeToggle data-test="header-assistant-mode-toggle" />

      <!-- Transport controls: drive the active queued run when one is
           live, otherwise send the currently loaded gcode directly.
           Hidden entirely when nothing is loaded and no run is active
           so the header stays uncluttered for layout-only sessions. -->
      <div
        v-if="canPlay || canStop"
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

      <button
        type="button"
        class="flex items-center gap-1.5 rounded border px-2.5 py-1 text-xs transition"
        :class="
          workshopOn
            ? 'border-amber-700 bg-amber-950/40 text-amber-200 hover:bg-amber-900/40'
            : 'border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700'
        "
        :title="t('header.workshop')"
        :aria-label="t('header.workshop')"
        :aria-pressed="workshopOn"
        data-test="header-workshop-toggle"
        @click="toggleWorkshop"
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
          <polyline points="15 3 21 3 21 9" />
          <polyline points="9 21 3 21 3 15" />
          <line x1="21" y1="3" x2="14" y2="10" />
          <line x1="3" y1="21" x2="10" y2="14" />
        </svg>
        <span class="hidden sm:inline">{{ t('header.workshop') }}</span>
      </button>

      <button
        type="button"
        class="flex items-center gap-1.5 rounded border px-2.5 py-1 text-xs transition"
        :class="
          plotterStatus.connected
            ? 'border-emerald-700 bg-emerald-950/40 text-emerald-200 hover:bg-emerald-900/40'
            : 'border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700'
        "
        :title="t('header.plotter')"
        :aria-label="t('header.plotter')"
        @click="ui.openPlotterDrawer()"
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
          <rect x="3" y="6" width="18" height="12" rx="1" />
          <path d="M7 10h10" />
          <path d="M12 14v4" />
          <circle cx="7" cy="14" r="0.5" />
        </svg>
        <span class="hidden sm:inline">{{ t('header.plotter') }}</span>
        <MachineStatusPill />
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
