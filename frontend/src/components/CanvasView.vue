<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'
import { useUiStore, type CanvasTab } from '../stores/ui'
import SheetPreview from './SheetPreview.vue'
import Simulator from './Simulator.vue'
import PlotterControl from './PlotterControl.vue'
import PlanRail from './PlanRail.vue'
import SimRail from './SimRail.vue'
import AppFooter from './AppFooter.vue'

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
    {
      id: 'simulator',
      label: t('canvas.simulator'),
      available: Boolean(job.gcode) && canSimulate.value,
    },
    { id: 'plotter', label: t('canvas.plotter'), available: true },
  ],
)

function select(tab: CanvasTab): void {
  canvasTab.value = tab
}

// "Start print" lives in the simulator header so the operator can fire
// the job straight from the preview they just reviewed. It mirrors the
// header transport's direct-send path: requires a live connection + a
// generated G-code, then sends after a confirmation.
const canStartPrint = computed(() => Boolean(job.gcode) && plotterStatus.value.connected)

async function startPrint(): Promise<void> {
  if (!job.gcode || !plotterStatus.value.connected) return
  const confirmed = await confirmAction({
    title: t('confirm.sendJobTitle'),
    message: t('confirm.sendJobMsg'),
    confirmLabel: t('plotter.sendJob'),
    cancelLabel: t('confirm.cancel'),
  })
  if (confirmed) await plotter.run(job.gcode)
}
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

      <!-- Simulator-tab header action: send the reviewed job to the
           plotter. Disabled (greyed) until both a G-code and a live
           connection are available. -->
      <button
        v-if="canvasTab === 'simulator'"
        type="button"
        class="ml-auto flex items-center gap-1 rounded bg-emerald-600 px-3 py-1 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
        :disabled="!canStartPrint"
        :title="plotterStatus.connected ? t('plotter.startPrint') : t('plotter.manualDisconnected')"
        data-test="simulator-start-print"
        @click="startPrint"
      >
        <span aria-hidden="true">▶</span>
        {{ t('plotter.startPrint') }}
      </button>
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
      <div v-show="canvasTab === 'simulator'" class="flex h-full min-h-0">
        <div class="flex min-h-0 flex-1 flex-col">
          <Simulator v-if="canSimulate && job.gcode" />
          <p v-else-if="!canSimulate" class="text-sm text-slate-500">
            {{ t('canvas.simulatorUnavailable') }}
          </p>
          <p v-else class="text-sm text-slate-500">{{ t('canvas.gcodeEmpty') }}</p>
        </div>
        <SimRail v-if="canSimulate && job.gcode" />
      </div>
      <div v-show="canvasTab === 'plotter'" class="flex h-full min-h-0 flex-col">
        <PlotterControl />
      </div>
    </div>

    <!-- Metrics footer (size / scale / estimate / pen changes) is scoped
         to the canvas column so it spans the plan/simulation/plotter area
         only, not the file library. Self-hides when no job is loaded. -->
    <AppFooter />
  </section>
</template>
