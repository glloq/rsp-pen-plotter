<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'
import JogControls from './JogControls.vue'

const { t } = useI18n()
const plotter = usePlotterStore()
const job = useJobStore()
const { status, port, baudrate, error, progress } = storeToRefs(plotter)

function sendJob(): void {
  if (job.gcode) plotter.run(job.gcode)
}
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800 p-4 space-y-3">
    <h2 class="text-sm uppercase tracking-wide text-slate-400">{{ t('plotter.title') }}</h2>

    <div v-if="!status.connected" class="space-y-2">
      <input
        v-model="port"
        placeholder="/dev/ttyUSB0"
        class="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-sm text-slate-100"
      />
      <input
        v-model.number="baudrate"
        type="number"
        class="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-sm text-slate-100"
      />
      <button
        type="button"
        class="w-full rounded bg-emerald-600 hover:bg-emerald-500 px-4 py-2 text-sm font-medium text-white"
        @click="plotter.connect()"
      >
        {{ t('plotter.connect') }}
      </button>
    </div>

    <div v-else class="space-y-3">
      <div class="flex items-center justify-between text-sm">
        <span class="text-emerald-300">{{ t('plotter.connected') }}</span>
        <button class="text-slate-400 hover:text-slate-200" @click="plotter.disconnect()">
          {{ t('plotter.disconnect') }}
        </button>
      </div>

      <JogControls />

      <div class="flex flex-wrap gap-2">
        <button
          class="rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-1 text-sm text-white disabled:opacity-50"
          :disabled="!job.gcode"
          @click="sendJob"
        >
          {{ t('plotter.sendJob') }}
        </button>
        <button class="rounded bg-slate-700 px-3 py-1 text-sm text-slate-100" @click="plotter.pause()">
          {{ t('plotter.pause') }}
        </button>
        <button class="rounded bg-slate-700 px-3 py-1 text-sm text-slate-100" @click="plotter.resume()">
          {{ t('plotter.resume') }}
        </button>
        <button class="rounded bg-red-700 px-3 py-1 text-sm text-white" @click="plotter.abort()">
          {{ t('plotter.abort') }}
        </button>
      </div>

      <div>
        <div class="mb-1 flex justify-between text-xs text-slate-400">
          <span>{{ status.state }}</span>
          <span>{{ status.acked }} / {{ status.total }}</span>
        </div>
        <div class="h-1.5 w-full overflow-hidden rounded bg-slate-700">
          <div class="h-full bg-emerald-500" :style="{ width: `${progress * 100}%` }" />
        </div>
      </div>
    </div>

    <p v-if="error" class="text-sm text-red-400">{{ error }}</p>
  </div>
</template>
