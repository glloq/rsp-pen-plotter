<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { usePlotterStore } from '../stores/plotter'
import { useUiStore } from '../stores/ui'
import CameraView from './CameraView.vue'
import JogControls from './JogControls.vue'

// Plotter tab: the workshop camera feed (top) above the manual cockpit.
// The generated-G-code view and the saved-files library moved out to the
// Simulation and Files tabs respectively, so this tab stays focused on
// driving the machine by hand.
const { t } = useI18n()
const plotter = usePlotterStore()
const ui = useUiStore()
const { status, error } = storeToRefs(plotter)
</script>

<template>
  <div class="flex h-full min-h-0 flex-col gap-2">
    <!-- CAMERA — live workshop feed above the manual cockpit. Always
         present: shows the configured stream, or a configure-hint that
         links into System settings when no camera is set up. -->
    <CameraView />

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
  </div>
</template>
