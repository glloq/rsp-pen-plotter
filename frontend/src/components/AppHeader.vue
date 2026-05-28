<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'
import { useQueueStore } from '../stores/queue'
import { useUiModeStore } from '../stores/uiMode'
import { useUiStore } from '../stores/ui'
import { useWorkspacesStore } from '../stores/workspaces'
import AssistantModeToggle from './AssistantModeToggle.vue'
import MachineStatusPill from './MachineStatusPill.vue'

const { t } = useI18n()
const ui = useUiStore()
const uiMode = useUiModeStore()
const plotter = usePlotterStore()
const queue = useQueueStore()
const job = useJobStore()
const workspaces = useWorkspacesStore()
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

function toggleWorkshop(): void {
  uiMode.setFlag('workshopMode', !uiMode.isFlagEnabled('workshopMode'))
}

const modalV2On = computed(() => uiMode.isFlagEnabled('modalV2'))
function toggleModalV2(): void {
  uiMode.setFlag('modalV2', !modalV2On.value)
}

const wsMenuOpen = ref(false)
function onWorkspaceChange(event: Event): void {
  const target = event.target as HTMLSelectElement
  workspaces.setActive(target.value)
}
function saveAsCurrent(): void {
  const name = window.prompt(t('workspaces.namePrompt'))
  if (name) workspaces.saveAs(name, [...workspaces.active.panels])
  wsMenuOpen.value = false
}
function renameCurrent(): void {
  const current = workspaces.active
  if (current.builtin) return
  const name = window.prompt(t('workspaces.namePrompt'), current.name)
  if (name) workspaces.rename(current.id, name)
  wsMenuOpen.value = false
}
function removeCurrent(): void {
  const current = workspaces.active
  if (current.builtin) return
  if (window.confirm(t('workspaces.removeConfirm', { name: current.name }))) {
    workspaces.remove(current.id)
  }
  wsMenuOpen.value = false
}
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
      <!-- Workspace switcher (roadmap D.3 + C wire). Built-in
           presets ship with non-editable names; custom workspaces
           expose Save as / Rename / Remove through the … menu. -->
      <div class="relative flex items-center gap-1" data-test="header-workspaces">
        <label class="sr-only" for="header-workspace-select">
          {{ t('workspaces.label') }}
        </label>
        <select
          id="header-workspace-select"
          class="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 hover:bg-slate-700"
          :value="workspaces.activeId"
          data-test="header-workspace-select"
          @change="onWorkspaceChange"
        >
          <option v-for="ws in workspaces.all" :key="ws.id" :value="ws.id">
            {{ ws.name }}
          </option>
        </select>
        <button
          type="button"
          class="rounded border border-slate-700 bg-slate-800 px-1.5 py-1 text-xs text-slate-200 hover:bg-slate-700"
          :aria-label="t('workspaces.menu')"
          data-test="header-workspace-menu"
          @click="wsMenuOpen = !wsMenuOpen"
        >
          ⋯
        </button>
        <div
          v-if="wsMenuOpen"
          class="absolute right-0 top-full z-50 mt-1 w-44 rounded border border-slate-700 bg-slate-800 py-1 text-xs text-slate-200 shadow-xl"
        >
          <button
            type="button"
            class="block w-full px-3 py-1.5 text-left hover:bg-slate-700"
            data-test="workspace-save-as"
            @click="saveAsCurrent"
          >
            {{ t('workspaces.saveAs') }}
          </button>
          <button
            type="button"
            class="block w-full px-3 py-1.5 text-left hover:bg-slate-700 disabled:opacity-40"
            :disabled="workspaces.active.builtin"
            data-test="workspace-rename"
            @click="renameCurrent"
          >
            {{ t('workspaces.rename') }}
          </button>
          <button
            type="button"
            class="block w-full px-3 py-1.5 text-left text-red-300 hover:bg-slate-700 disabled:opacity-40"
            :disabled="workspaces.active.builtin"
            data-test="workspace-remove"
            @click="removeCurrent"
          >
            {{ t('workspaces.remove') }}
          </button>
        </div>
      </div>

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
          modalV2On
            ? 'border-sky-700 bg-sky-950/40 text-sky-200 hover:bg-sky-900/40'
            : 'border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700'
        "
        :title="t('header.modalV2')"
        :aria-pressed="modalV2On"
        data-test="header-modal-v2-toggle"
        @click="toggleModalV2"
      >
        <span class="hidden sm:inline">{{ t('header.modalV2') }}</span>
        <span class="sm:hidden">V2</span>
      </button>

      <button
        type="button"
        class="flex items-center gap-1.5 rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700"
        :title="t('header.workshop')"
        :aria-label="t('header.workshop')"
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
          <path d="M3 7h4l2-3h6l2 3h4v13H3z" />
          <circle cx="12" cy="13" r="3" />
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
