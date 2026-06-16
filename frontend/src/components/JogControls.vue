<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'

const { t } = useI18n()
const plotter = usePlotterStore()
const job = useJobStore()
const step = ref(10)
const targetX = ref(0)
const targetY = ref(0)

function jog(dx: number, dy: number): void {
  plotter.jog(dx * step.value, dy * step.value, job.selectedProfileName)
}

async function home(): Promise<void> {
  const confirmed = await confirmAction({
    title: t('confirm.homeTitle'),
    message: t('confirm.homeMsg'),
    confirmLabel: t('plotter.home'),
    cancelLabel: t('confirm.cancel'),
  })
  if (confirmed) plotter.home(job.selectedProfileName)
}

function gotoTarget(): void {
  plotter.goto(targetX.value, targetY.value, job.selectedProfileName)
}

const corners = computed(() => {
  const ws = job.selectedProfile?.workspace
  if (!ws) return []
  return [
    { label: '↙', x: ws.x_min, y: ws.y_min },
    { label: '↘', x: ws.x_max, y: ws.y_min },
    { label: '↖', x: ws.x_min, y: ws.y_max },
    { label: '↗', x: ws.x_max, y: ws.y_max },
  ]
})
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
      <button
        class="rounded bg-slate-700 hover:bg-slate-600 py-2 text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
        :aria-label="t('plotter.jogUp')"
        :title="t('plotter.jogUp')"
        :disabled="plotter.movementBusy"
        @click="jog(0, 1)"
      >
        ↑
      </button>
      <span />
      <button
        class="rounded bg-slate-700 hover:bg-slate-600 py-2 text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
        :aria-label="t('plotter.jogLeft')"
        :title="t('plotter.jogLeft')"
        :disabled="plotter.movementBusy"
        @click="jog(-1, 0)"
      >
        ←
      </button>
      <button
        class="rounded bg-slate-700 hover:bg-slate-600 py-2 text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
        :aria-label="t('plotter.home')"
        :title="t('plotter.home')"
        :disabled="plotter.movementBusy"
        @click="home"
      >
        ⌂
      </button>
      <button
        class="rounded bg-slate-700 hover:bg-slate-600 py-2 text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
        :aria-label="t('plotter.jogRight')"
        :title="t('plotter.jogRight')"
        :disabled="plotter.movementBusy"
        @click="jog(1, 0)"
      >
        →
      </button>
      <span />
      <button
        class="rounded bg-slate-700 hover:bg-slate-600 py-2 text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
        :aria-label="t('plotter.jogDown')"
        :title="t('plotter.jogDown')"
        :disabled="plotter.movementBusy"
        @click="jog(0, -1)"
      >
        ↓
      </button>
      <span />
    </div>

    <div class="space-y-1">
      <span class="text-sm text-slate-400">{{ t('plotter.goto') }}</span>
      <div class="flex items-center gap-1">
        <input
          v-model.number="targetX"
          type="number"
          step="any"
          placeholder="X"
          class="w-16 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        />
        <input
          v-model.number="targetY"
          type="number"
          step="any"
          placeholder="Y"
          class="w-16 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
        />
        <button
          class="rounded bg-slate-700 px-3 py-1 text-slate-100 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed"
          :disabled="plotter.movementBusy"
          @click="gotoTarget"
        >
          {{ t('plotter.go') }}
        </button>
      </div>
      <div v-if="corners.length" class="flex gap-1">
        <button
          v-for="corner in corners"
          :key="corner.label"
          class="flex-1 rounded bg-slate-700 py-1 text-slate-100 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed"
          :aria-label="t('plotter.gotoCorner', { x: corner.x, y: corner.y })"
          :title="`X${corner.x} Y${corner.y}`"
          :disabled="plotter.movementBusy"
          @click="plotter.goto(corner.x, corner.y, job.selectedProfileName)"
        >
          {{ corner.label }}
        </button>
      </div>
    </div>
  </div>
</template>
