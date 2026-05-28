<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { useUiStore, type CanvasTab } from '../stores/ui'
import SheetPreview from './SheetPreview.vue'
import Simulator from './Simulator.vue'
import GcodePreview from './GcodePreview.vue'
import PlanRail from './PlanRail.vue'
import SimRail from './SimRail.vue'
import AppFooter from './AppFooter.vue'

const { t } = useI18n()
const job = useJobStore()
const ui = useUiStore()
const { canvasTab } = storeToRefs(ui)

const canSimulate = computed(() => job.selectedProfile?.gcode_dialect !== 'ebb')

const tabs = computed<Array<{ id: CanvasTab; label: string; available: boolean; hint?: string }>>(
  () => [
    { id: 'sheet', label: t('canvas.sheet'), available: true },
    {
      id: 'simulator',
      label: t('canvas.simulator'),
      available: Boolean(job.gcode) && canSimulate.value,
    },
    { id: 'gcode', label: t('canvas.gcode'), available: Boolean(job.gcode) },
  ],
)

function select(tab: CanvasTab): void {
  canvasTab.value = tab
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
        @click="select(tab.id)"
      >
        {{ tab.label }}
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
      <div v-show="canvasTab === 'gcode'" class="flex h-full min-h-0 flex-col">
        <GcodePreview v-if="job.gcode" />
        <p v-else class="text-sm text-slate-500">{{ t('canvas.gcodeEmpty') }}</p>
      </div>
    </div>

    <!-- Metrics footer (size / scale / estimate / pen changes) is scoped
         to the canvas column so it spans the plan/simulation/gcode area
         only, not the file library. Self-hides when no job is loaded. -->
    <AppFooter />
  </section>
</template>
