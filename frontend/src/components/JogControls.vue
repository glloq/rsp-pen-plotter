<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'

// Compact Repetier-style manual cockpit: an X/Y jog cross (with Home in
// the centre) on the left, a Z jog column (motorised Z), and the pen
// servo lift/lower beside it. One shared step selector drives X/Y/Z.
// Deliberately no "go to point / corners" — this stays minimal.

const { t } = useI18n()
const plotter = usePlotterStore()
const job = useJobStore()
const step = ref(10)

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

function jogZ(dz: number): void {
  plotter.jog(0, 0, job.selectedProfileName, dz * step.value)
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

const jogBtn =
  'rounded bg-slate-700 hover:bg-slate-600 py-1 text-sm text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed'
const axisBtn =
  'rounded bg-slate-700 hover:bg-slate-600 px-2 py-1 text-xs font-medium text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed'
const penBtn =
  'rounded bg-slate-700 hover:bg-slate-600 px-2 py-1 text-[11px] text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed'
</script>

<template>
  <div class="space-y-2">
    <div class="flex items-start gap-3">
      <!-- X/Y jog cross with Home in the centre -->
      <div class="grid w-[5.5rem] shrink-0 grid-cols-3 gap-1">
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

      <!-- Z jog column (motorised Z) -->
      <div class="flex flex-col items-stretch gap-1">
        <span class="text-center text-[10px] uppercase tracking-wider text-slate-500">Z</span>
        <button
          :class="axisBtn"
          :aria-label="t('plotter.jogZUp')"
          :title="t('plotter.jogZUp')"
          :disabled="controlsDisabled"
          data-test="jog-z-up"
          @click="jogZ(1)"
        >
          Z+
        </button>
        <button
          :class="axisBtn"
          :aria-label="t('plotter.jogZDown')"
          :title="t('plotter.jogZDown')"
          :disabled="controlsDisabled"
          data-test="jog-z-down"
          @click="jogZ(-1)"
        >
          Z−
        </button>
      </div>

      <!-- Pen servo lift / lower -->
      <div class="flex min-w-0 flex-1 flex-col gap-1">
        <span class="text-[10px] uppercase tracking-wider text-slate-500">{{
          t('plotter.penControl')
        }}</span>
        <button
          type="button"
          :class="penBtn"
          :disabled="controlsDisabled || !penUpCmd"
          :title="penUpCmd"
          data-test="manual-pen-up"
          @click="penUp"
        >
          ▲ {{ t('plotter.penUp') }}
        </button>
        <button
          type="button"
          :class="penBtn"
          :disabled="controlsDisabled || !penDownCmd"
          :title="penDownCmd"
          data-test="manual-pen-down"
          @click="penDown"
        >
          ▼ {{ t('plotter.penDown') }}
        </button>
        <p v-if="!penUpCmd || !penDownCmd" class="text-[10px] leading-tight text-slate-500">
          {{ t('plotter.penCommandsMissing') }}
        </p>
      </div>
    </div>

    <!-- Shared step size for X / Y / Z -->
    <label class="flex items-center gap-1.5 text-[11px] text-slate-400">
      <span>{{ t('plotter.step') }}</span>
      <select
        v-model.number="step"
        :disabled="controlsDisabled"
        class="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[11px] text-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <option :value="0.1">0.1 mm</option>
        <option :value="1">1 mm</option>
        <option :value="10">10 mm</option>
        <option :value="50">50 mm</option>
      </select>
    </label>
  </div>
</template>
