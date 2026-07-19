<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useLaunchCurrentJob } from '../composables/useLaunchCurrentJob'
import { useSaveCurrentGcode } from '../composables/useSaveCurrentGcode'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'
import { useUiStore, type CanvasTab } from '../stores/ui'
import SheetPreview from './SheetPreview.vue'
import Simulator from './Simulator.vue'
import PlotterControl from './PlotterControl.vue'
import PlanRail from './PlanRail.vue'
import SimRail from './SimRail.vue'
import GcodePreview from './GcodePreview.vue'
import GcodeFilesPanel from './GcodeFilesPanel.vue'
import AppFooter from './AppFooter.vue'
import PrimaryWorkflowAction from './PrimaryWorkflowAction.vue'

const { t } = useI18n()
const job = useJobStore()
const plotter = usePlotterStore()
const ui = useUiStore()
const { canvasTab } = storeToRefs(ui)
const { status: plotterStatus } = storeToRefs(plotter)

const canSimulate = computed(() => job.selectedProfile?.gcode_dialect !== 'ebb')

const tabs = computed<Array<{ id: CanvasTab; label: string; available: boolean; hint?: string }>>(
  () => [
    { id: 'sheet', label: t('canvas.sheet'), available: true },
    // Available as soon as a G-code exists — even for dialects the visual
    // simulator can't replay (ebb): the tab still hosts the program text,
    // the Save action and the Start-print button.
    { id: 'simulator', label: t('canvas.simulator'), available: Boolean(job.gcode) },
    // Saved-programs library — always reachable, independent of the
    // current job.
    { id: 'files', label: t('canvas.files'), available: true },
    { id: 'plotter', label: t('canvas.plotter'), available: true },
  ],
)

function select(tab: CanvasTab): void {
  canvasTab.value = tab
}

// Save the current program into the library — the simulator tab's
// secondary action, beside "Start print". Lives here (shared composable)
// so the odometer bookkeeping stays in one place.
const { canSave, saving, saveCurrent } = useSaveCurrentGcode()

// Collapsible current-G-code panel under the simulator preview. Defaults
// open so the operator sees the program they're about to save or print;
// the toggle label carries the line count.
const gcodeOpen = ref(true)
const gcodeLineCount = computed(() => (job.gcode ? job.gcode.split('\n').length : 0))

// "Start print" lives in the simulator header so the operator can fire
// the job straight from the preview they just reviewed. It shares the
// header transport's launch path (gate → confirm → run → ink-odometer
// commit) via ``useLaunchCurrentJob``. Disabled while the machine is busy
// (running / paused) so the operator can't re-send mid-plot — which would
// also double-count ink — mirroring the header, which flips Play → Pause
// during a run.
const canStartPrint = computed(
  () =>
    Boolean(job.gcode) &&
    plotterStatus.value.connected &&
    plotterStatus.value.state !== 'running' &&
    plotterStatus.value.state !== 'paused',
)
const { launch: startPrint } = useLaunchCurrentJob()
</script>

<template>
  <section
    class="flex min-h-0 flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-800"
  >
    <nav class="flex items-center gap-1 border-b border-slate-700 bg-slate-900/40 px-2 py-1.5">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        :disabled="!tab.available"
        class="rounded px-3 py-1 text-sm transition"
        :class="
          canvasTab === tab.id
            ? 'bg-slate-700 text-white'
            : tab.available
              ? 'text-slate-300 hover:bg-slate-800'
              : 'text-slate-600 cursor-not-allowed'
        "
        :data-test="`canvas-tab-${tab.id}`"
        @click="select(tab.id)"
      >
        {{ tab.label }}
      </button>

      <!-- Simulator-tab header actions: save the reviewed program into the
           library, or send it straight to the plotter. Save needs a
           G-code; Start print also needs a live connection. -->
      <div v-if="canvasTab === 'simulator'" class="ml-auto flex items-center gap-2">
        <button
          type="button"
          class="flex items-center gap-1 rounded border border-sky-600 px-3 py-1 text-sm font-medium text-sky-200 hover:bg-sky-600/20 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!canSave || saving"
          data-test="simulator-save-gcode"
          @click="saveCurrent"
        >
          <span aria-hidden="true">💾</span>
          {{ t('plotter.saveGcode') }}
        </button>
        <button
          type="button"
          class="flex items-center gap-1 rounded bg-emerald-600 px-3 py-1 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!canStartPrint"
          :title="
            plotterStatus.connected ? t('plotter.startPrint') : t('plotter.manualDisconnected')
          "
          data-test="simulator-start-print"
          @click="startPrint"
        >
          <span aria-hidden="true">▶</span>
          {{ t('plotter.startPrint') }}
        </button>
      </div>
    </nav>

    <div class="relative flex min-h-0 flex-1 flex-col overflow-hidden p-3">
      <!-- The sheet tab is always mounted so the workspace grid stays
           visible and the drop target exists even before any file is
           imported. Other tabs keep their own empty-state messaging. -->
      <div v-show="canvasTab === 'sheet'" class="flex h-full min-h-0">
        <div class="flex min-h-0 flex-1">
          <SheetPreview />
        </div>
        <PlanRail />
      </div>
      <div v-show="canvasTab === 'simulator'" class="flex h-full min-h-0 flex-col gap-2">
        <div class="flex min-h-0 flex-1">
          <div class="flex min-h-0 flex-1 flex-col">
            <Simulator v-if="canSimulate && job.gcode" />
            <p v-else-if="!canSimulate" class="text-sm text-slate-500">
              {{ t('canvas.simulatorUnavailable') }}
            </p>
            <p v-else class="text-sm text-slate-500">{{ t('canvas.gcodeEmpty') }}</p>
          </div>
          <SimRail v-if="canSimulate && job.gcode" />
        </div>

        <!-- Current generated G-code — the program about to be saved or
             printed. Collapsible so the simulator canvas keeps the height
             by default; the toggle carries the line count. -->
        <div class="shrink-0 overflow-hidden rounded-lg border border-slate-700 bg-slate-900">
          <button
            type="button"
            class="flex w-full items-center justify-between px-4 py-2 text-left text-sm text-slate-300 hover:bg-slate-800/60"
            :aria-expanded="gcodeOpen"
            data-test="simulator-gcode-toggle"
            @click="gcodeOpen = !gcodeOpen"
          >
            <span class="flex items-center gap-2">
              <span aria-hidden="true" class="text-xs">{{ gcodeOpen ? '▾' : '▸' }}</span>
              <span class="uppercase tracking-wide">{{ t('plotter.gcodeSection') }}</span>
              <span v-if="job.gcode" class="text-xs text-slate-500"
                >({{ gcodeLineCount }} {{ t('gcode.lines') }})</span
              >
            </span>
            <span v-if="!job.gcode" class="text-xs text-slate-500">{{
              t('canvas.gcodeEmpty')
            }}</span>
          </button>
          <div
            v-show="gcodeOpen"
            class="h-64 border-t border-slate-700"
            data-test="simulator-gcode-body"
          >
            <GcodePreview v-if="job.gcode" />
            <p v-else class="p-4 text-sm text-slate-500">{{ t('canvas.gcodeEmpty') }}</p>
          </div>
        </div>
      </div>

      <!-- Saved-programs library: the full list of stored G-code files,
           pick one and print it on demand. -->
      <div v-show="canvasTab === 'files'" class="flex h-full min-h-0 flex-col overflow-y-auto">
        <div class="rounded-lg border border-slate-700 bg-slate-900 p-3">
          <h3 class="mb-2 text-sm font-semibold text-slate-100">{{ t('gcodeFiles.title') }}</h3>
          <GcodeFilesPanel />
        </div>
      </div>

      <div v-show="canvasTab === 'plotter'" class="flex h-full min-h-0 flex-col">
        <PlotterControl />
      </div>
    </div>

    <!-- Single contextual primary action (UX vague 2): one bar, one
         button, label follows the workflow step. Sits above the metrics
         footer so it's always at the same spot under the plan. -->
    <PrimaryWorkflowAction />

    <!-- Metrics footer (size / scale / estimate / pen changes) is scoped
         to the canvas column so it spans the plan/simulation/plotter area
         only, not the file library. Self-hides when no job is loaded. -->
    <AppFooter />
  </section>
</template>
