<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'
import { useUiStore } from '../stores/ui'
import GcodePreview from './GcodePreview.vue'
import JogControls from './JogControls.vue'
import GcodeFilesPanel from './GcodeFilesPanel.vue'

const { t } = useI18n()
const job = useJobStore()
const plotter = usePlotterStore()
const ui = useUiStore()
const { status, error } = storeToRefs(plotter)

const canSend = computed(() => Boolean(job.gcode))

// Collapsible generated-G-code panel at the bottom of the tab. Defaults
// to collapsed so the manual controls stay front-and-centre; the count
// in the toggle label hints that there's something to expand.
const gcodeOpen = ref(false)
const gcodeLineCount = computed(() => (job.gcode ? job.gcode.split('\n').length : 0))
</script>

<template>
  <div class="flex h-full min-h-0 flex-col gap-2">
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

      <!-- G-code file library: save the current program, then pick one and
           print it on demand. Always visible so the operator can manage
           saved programs even while disconnected. -->
      <section class="mt-3 space-y-1.5">
        <h4 class="px-1 text-xs uppercase tracking-wider text-slate-500">
          {{ t('gcodeFiles.title') }}
        </h4>
        <GcodeFilesPanel />
      </section>
    </div>

    <!-- COLLAPSIBLE G-CODE PANEL (bottom of the tab) -->
    <div class="shrink-0 overflow-hidden rounded-lg border border-slate-700 bg-slate-900">
      <button
        type="button"
        class="flex w-full items-center justify-between px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-800/60"
        :aria-expanded="gcodeOpen"
        data-test="plotter-gcode-toggle"
        @click="gcodeOpen = !gcodeOpen"
      >
        <span class="flex items-center gap-2">
          <span aria-hidden="true" class="text-xs">{{ gcodeOpen ? '▾' : '▸' }}</span>
          <span class="uppercase tracking-wide">{{ t('plotter.gcodeSection') }}</span>
          <span v-if="canSend" class="text-xs text-slate-500"
            >({{ gcodeLineCount }} {{ t('gcode.lines') }})</span
          >
        </span>
        <span v-if="!canSend" class="text-xs text-slate-500">{{ t('canvas.gcodeEmpty') }}</span>
      </button>
      <div v-show="gcodeOpen" class="h-64 border-t border-slate-700" data-test="plotter-gcode-body">
        <GcodePreview v-if="canSend" />
        <p v-else class="p-4 text-sm text-slate-500">{{ t('canvas.gcodeEmpty') }}</p>
      </div>
    </div>
  </div>
</template>
