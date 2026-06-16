<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'

// Compact manual-control cockpit: XY jog pad + step on the left, pen
// up/down + go-to + workspace corners on the right. Sized to take the
// minimum room on the Plotter tab (CNC / laser / 3D-printer style) so the
// print queue keeps the space below.

const { t } = useI18n()
const plotter = usePlotterStore()
const job = useJobStore()
const step = ref(10)
const targetX = ref(0)
const targetY = ref(0)

// Manual moves need a live, idle machine. The cockpit stays mounted at
// all times and greys out whenever the head can't be driven: no
// connection, a move already in flight, or a job running / paused (which
// owns the head).
const controlsDisabled = computed(
  () =>
    !plotter.status.connected ||
    plotter.movementBusy ||
    plotter.status.state === 'running' ||
    plotter.status.state === 'paused',
)

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

const penUpCmd = computed(() => job.selectedProfile?.pen_up_command ?? '')
const penDownCmd = computed(() => job.selectedProfile?.pen_down_command ?? '')

async function penUp(): Promise<void> {
  if (!penUpCmd.value) return
  await plotter.run(penUpCmd.value)
}

async function penDown(): Promise<void> {
  if (!penDownCmd.value) return
  await plotter.run(penDownCmd.value)
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

const jogBtn =
  'rounded bg-slate-700 hover:bg-slate-600 py-1 text-sm text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed'
const actBtn =
  'rounded bg-slate-700 hover:bg-slate-600 text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed'
const fieldCls =
  'rounded border border-slate-700 bg-slate-900 text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed'
</script>

<template>
  <div class="flex gap-2">
    <!-- LEFT: XY jog pad + step size -->
    <div class="shrink-0">
      <div class="grid w-[5.5rem] grid-cols-3 gap-1">
        <span />
        <button
          :class="jogBtn"
          :aria-label="t('plotter.jogUp')"
          :title="t('plotter.jogUp')"
          :disabled="controlsDisabled"
          @click="jog(0, 1)"
        >
          ↑
        </button>
        <span />
        <button
          :class="jogBtn"
          :aria-label="t('plotter.jogLeft')"
          :title="t('plotter.jogLeft')"
          :disabled="controlsDisabled"
          @click="jog(-1, 0)"
        >
          ←
        </button>
        <button
          :class="jogBtn"
          :aria-label="t('plotter.home')"
          :title="t('plotter.home')"
          :disabled="controlsDisabled"
          @click="home"
        >
          ⌂
        </button>
        <button
          :class="jogBtn"
          :aria-label="t('plotter.jogRight')"
          :title="t('plotter.jogRight')"
          :disabled="controlsDisabled"
          @click="jog(1, 0)"
        >
          →
        </button>
        <span />
        <button
          :class="jogBtn"
          :aria-label="t('plotter.jogDown')"
          :title="t('plotter.jogDown')"
          :disabled="controlsDisabled"
          @click="jog(0, -1)"
        >
          ↓
        </button>
        <span />
      </div>
      <label class="mt-1 flex items-center justify-center gap-1 text-[10px] text-slate-400">
        <span>{{ t('plotter.step') }}</span>
        <select
          v-model.number="step"
          :disabled="controlsDisabled"
          :class="fieldCls"
          class="px-1 py-0.5 text-[10px]"
        >
          <option :value="1">1 mm</option>
          <option :value="10">10 mm</option>
          <option :value="50">50 mm</option>
        </select>
      </label>
    </div>

    <!-- RIGHT: pen lift, go-to coordinates, workspace corners -->
    <div class="flex min-w-0 flex-1 flex-col gap-1.5">
      <div class="flex gap-1.5">
        <button
          type="button"
          :class="actBtn"
          class="flex-1 px-1.5 py-1 text-[11px]"
          :disabled="controlsDisabled || !penUpCmd"
          :title="penUpCmd"
          data-test="manual-pen-up"
          @click="penUp"
        >
          ↑ {{ t('plotter.penUp') }}
        </button>
        <button
          type="button"
          :class="actBtn"
          class="flex-1 px-1.5 py-1 text-[11px]"
          :disabled="controlsDisabled || !penDownCmd"
          :title="penDownCmd"
          data-test="manual-pen-down"
          @click="penDown"
        >
          ↓ {{ t('plotter.penDown') }}
        </button>
      </div>
      <p v-if="!penUpCmd || !penDownCmd" class="text-[10px] leading-tight text-slate-500">
        {{ t('plotter.penCommandsMissing') }}
      </p>

      <div class="flex items-center gap-1">
        <input
          v-model.number="targetX"
          type="number"
          step="any"
          placeholder="X"
          :disabled="controlsDisabled"
          :class="fieldCls"
          class="w-full min-w-0 px-1.5 py-0.5 text-[11px]"
        />
        <input
          v-model.number="targetY"
          type="number"
          step="any"
          placeholder="Y"
          :disabled="controlsDisabled"
          :class="fieldCls"
          class="w-full min-w-0 px-1.5 py-0.5 text-[11px]"
        />
        <button
          :class="actBtn"
          class="shrink-0 px-2 py-0.5 text-[11px]"
          :disabled="controlsDisabled"
          @click="gotoTarget"
        >
          {{ t('plotter.go') }}
        </button>
      </div>

      <div v-if="corners.length" class="flex gap-1">
        <button
          v-for="corner in corners"
          :key="corner.label"
          :class="actBtn"
          class="flex-1 py-0.5 text-[11px]"
          :aria-label="t('plotter.gotoCorner', { x: corner.x, y: corner.y })"
          :title="`X${corner.x} Y${corner.y}`"
          :disabled="controlsDisabled"
          @click="plotter.goto(corner.x, corner.y, job.selectedProfileName)"
        >
          {{ corner.label }}
        </button>
      </div>
    </div>
  </div>
</template>
