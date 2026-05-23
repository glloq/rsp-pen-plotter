<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { useUiStore, type CanvasTab } from '../stores/ui'
import SheetPreview from './SheetPreview.vue'
import SvgPreview from './SvgPreview.vue'
import Simulator from './Simulator.vue'
import GcodePreview from './GcodePreview.vue'
import PenStrip from './PenStrip.vue'

const { t } = useI18n()
const job = useJobStore()
const ui = useUiStore()
const { canvasTab } = storeToRefs(ui)

const canSimulate = computed(() => job.selectedProfile?.gcode_dialect !== 'ebb')

const tabs = computed<Array<{ id: CanvasTab; label: string; available: boolean; hint?: string }>>(() => [
  { id: 'sheet', label: t('canvas.sheet'), available: job.layers.length > 0 },
  { id: 'svg', label: t('canvas.svg'), available: Boolean(job.svg) },
  { id: 'simulator', label: t('canvas.simulator'), available: Boolean(job.gcode) && canSimulate.value },
  { id: 'gcode', label: t('canvas.gcode'), available: Boolean(job.gcode) },
])

function select(tab: CanvasTab): void {
  canvasTab.value = tab
}
</script>

<template>
  <section class="flex min-h-0 flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-800">
    <nav class="flex items-center gap-1 border-b border-slate-700 bg-slate-900/40 px-2 py-1.5">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        :disabled="!tab.available"
        class="rounded px-3 py-1 text-sm transition"
        :class="canvasTab === tab.id
          ? 'bg-slate-700 text-white'
          : tab.available
            ? 'text-slate-300 hover:bg-slate-800'
            : 'text-slate-600 cursor-not-allowed'"
        @click="select(tab.id)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <div class="relative min-h-0 flex-1 overflow-auto p-3">
      <div
        v-if="!job.layers.length"
        class="flex h-full flex-col items-center justify-center gap-3 text-center text-slate-500"
      >
        <div class="text-5xl text-slate-700" aria-hidden="true">⤵</div>
        <p class="text-base text-slate-300">{{ t('canvas.empty') }}</p>
        <p class="max-w-sm text-xs text-slate-600">{{ t('canvas.emptyHint') }}</p>
        <p class="text-[10px] uppercase tracking-wider text-slate-700">{{ t('canvas.emptyFormats') }}</p>
      </div>

      <template v-else>
        <div v-show="canvasTab === 'sheet'">
          <SheetPreview />
        </div>
        <div v-if="canvasTab === 'svg'" class="h-full">
          <SvgPreview />
        </div>
        <div v-show="canvasTab === 'simulator'">
          <Simulator v-if="canSimulate" />
          <p v-else class="text-sm text-slate-500">{{ t('canvas.simulatorUnavailable') }}</p>
        </div>
        <div v-show="canvasTab === 'gcode'">
          <GcodePreview />
          <p v-if="!job.gcode" class="text-sm text-slate-500">{{ t('canvas.gcodeEmpty') }}</p>
        </div>
      </template>
    </div>

    <PenStrip />
  </section>
</template>
