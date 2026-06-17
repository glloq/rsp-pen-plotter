<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { getPlotterCommands } from '../api/client'
import { usePlotterStore } from '../stores/plotter'
import { useUiStore } from '../stores/ui'
import CameraView from './CameraView.vue'
import JogControls from './JogControls.vue'
import TimelapsePanel from './TimelapsePanel.vue'

// Plotter tab: the workshop camera feed (top) above the manual cockpit,
// with a collapsible "commands sent" history at the bottom. The
// generated-G-code view and the saved-files library moved out to the
// Simulation and Files tabs respectively, so this tab stays focused on
// driving the machine by hand.
const { t } = useI18n()
const plotter = usePlotterStore()
const ui = useUiStore()
const { status, error } = storeToRefs(plotter)

// Command history — collapsed by default. Polls the rolling server-side
// log of G-code actually written to the device only while expanded, so
// it's free when closed.
const historyOpen = ref(false)
const commandLog = ref<string[]>([])
const commandLogText = computed(() => commandLog.value.join('\n'))
const historyBody = ref<HTMLElement | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

async function refreshCommandLog(): Promise<void> {
  try {
    commandLog.value = await getPlotterCommands()
    // Keep the newest line in view (terminal-style tail).
    await nextTick()
    if (historyBody.value) historyBody.value.scrollTop = historyBody.value.scrollHeight
  } catch {
    // Transient fetch failure (e.g. disconnected) — keep the last log.
  }
}

function stopPolling(): void {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// Poll only while the history is open AND the Plotter tab is actually on
// screen — the tab stays mounted via v-show, so without the tab check the
// log would keep polling in the background from other tabs.
const shouldPoll = computed(() => historyOpen.value && ui.canvasTab === 'plotter')
watch(shouldPoll, (poll) => {
  if (poll) {
    void refreshCommandLog()
    pollTimer = setInterval(() => void refreshCommandLog(), 1500)
  } else {
    stopPolling()
  }
})

onUnmounted(stopPolling)
</script>

<template>
  <div class="flex h-full min-h-0 flex-col gap-2">
    <!-- CAMERA — live workshop feed above the manual cockpit. Always
         present: shows the configured stream, or a configure-hint that
         links into System settings when no camera is set up. -->
    <CameraView />

    <!-- TIMELAPSE — capture frames from a camera + export an MP4.
         Collapsed by default. -->
    <TimelapsePanel />

    <div
      class="flex min-h-0 flex-1 flex-col overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 p-3"
    >
      <!-- Tab toolbar: connection status + a connect shortcut + entry into
           the settings modal (connection, profile, colours, macros, queue).
           This title labels the manual cockpit directly below it. -->
      <header class="mb-2 flex items-center justify-between gap-2">
        <h3 class="flex items-center gap-2 text-sm font-semibold text-slate-100">
          {{ t('plotter.tabManual') }}
          <span class="flex items-center gap-1.5 text-[11px] font-normal">
            <span
              class="inline-block h-1.5 w-1.5 rounded-full"
              :class="status.connected ? 'bg-emerald-400' : 'bg-slate-600'"
            />
            <span :class="status.connected ? 'text-emerald-300' : 'text-slate-500'">
              {{ status.connected ? t('plotter.connected') : t('machine.disconnected') }}
            </span>
          </span>
        </h3>
        <div class="flex items-center gap-1.5">
          <button
            v-if="!status.connected"
            type="button"
            class="rounded bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-500"
            data-test="plotter-connect-cta"
            :title="t('plotter.manualDisconnected')"
            @click="ui.openPlotterSettings('connection')"
          >
            {{ t('plotter.connect') }}
          </button>
          <button
            type="button"
            class="rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700"
            data-test="plotter-open-settings"
            @click="ui.openPlotterSettings()"
          >
            ⚙ {{ t('plotter.settingsTitle') }}
          </button>
        </div>
      </header>

      <!-- MANUAL CONTROL — always mounted (CNC / laser / 3D-printer style),
           greyed + disabled until a plotter is connected. The whole cockpit
           (jog pad + pen + go-to + corners) is one compact two-column card
           so the tab fits without scrolling. -->
      <div
        class="rounded-lg border border-slate-700 bg-slate-800 p-2 transition-opacity"
        :class="{ 'opacity-50': !status.connected }"
        :aria-disabled="!status.connected"
        data-test="manual-control"
      >
        <JogControls />
      </div>
      <p v-if="error" class="mt-1.5 text-xs text-red-400">{{ error }}</p>
    </div>

    <!-- COMMAND HISTORY — collapsible log of the G-code actually sent to
         the plotter (manual jogs / homing / pen + streamed job lines).
         Collapsed by default; polls only while open. -->
    <div class="shrink-0 overflow-hidden rounded-lg border border-slate-700 bg-slate-900">
      <button
        type="button"
        class="flex w-full items-center justify-between px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-800/60"
        :aria-expanded="historyOpen"
        data-test="plotter-history-toggle"
        @click="historyOpen = !historyOpen"
      >
        <span class="flex items-center gap-2">
          <span aria-hidden="true" class="text-xs">{{ historyOpen ? '▾' : '▸' }}</span>
          <span class="uppercase tracking-wide">{{ t('plotter.commandHistory') }}</span>
          <span v-if="commandLog.length" class="text-xs text-slate-500"
            >({{ commandLog.length }})</span
          >
        </span>
      </button>
      <div
        v-show="historyOpen"
        ref="historyBody"
        class="h-44 overflow-auto border-t border-slate-700 bg-slate-950"
        data-test="plotter-history-body"
      >
        <pre
          v-if="commandLog.length"
          class="p-2 text-[11px] font-mono leading-snug text-emerald-200 whitespace-pre-wrap"
          >{{ commandLogText }}</pre
        >
        <p v-else class="p-3 text-xs text-slate-500">{{ t('plotter.commandHistoryEmpty') }}</p>
      </div>
    </div>
  </div>
</template>
