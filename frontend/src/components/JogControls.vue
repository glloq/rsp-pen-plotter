<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'

const { t } = useI18n()
const plotter = usePlotterStore()
const job = useJobStore()
const step = ref(10)

function jog(dx: number, dy: number): void {
  plotter.jog(dx * step.value, dy * step.value, job.selectedProfileName)
}
</script>

<template>
  <div class="space-y-2">
    <div class="flex items-center gap-2 text-sm text-slate-400">
      <span>{{ t('plotter.step') }}</span>
      <select
        v-model.number="step"
        class="rounded bg-slate-900 border border-slate-700 px-2 py-1 text-slate-100"
      >
        <option :value="1">1 mm</option>
        <option :value="10">10 mm</option>
        <option :value="50">50 mm</option>
      </select>
    </div>
    <div class="grid grid-cols-3 gap-1 w-36">
      <span />
      <button class="rounded bg-slate-700 hover:bg-slate-600 py-2 text-slate-100" @click="jog(0, 1)">↑</button>
      <span />
      <button class="rounded bg-slate-700 hover:bg-slate-600 py-2 text-slate-100" @click="jog(-1, 0)">←</button>
      <button class="rounded bg-slate-700 hover:bg-slate-600 py-2 text-slate-100" @click="plotter.home(job.selectedProfileName)">⌂</button>
      <button class="rounded bg-slate-700 hover:bg-slate-600 py-2 text-slate-100" @click="jog(1, 0)">→</button>
      <span />
      <button class="rounded bg-slate-700 hover:bg-slate-600 py-2 text-slate-100" @click="jog(0, -1)">↓</button>
      <span />
    </div>
  </div>
</template>
