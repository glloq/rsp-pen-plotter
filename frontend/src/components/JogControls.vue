<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'

// Compact Repetier-style manual cockpit: an X/Y jog cross (⌂ centre =
// Home all), a motorised-Z jog column, the pen servo lift/lower, and
// per-axis Home X/Y/Z buttons. The step is a segmented button row (no
// dropdown) shared by X/Y/Z. Deliberately no "go to point / corners".

const { t } = useI18n()
const plotter = usePlotterStore()
const job = useJobStore()

const STEPS = [0.1, 0.5, 1, 10, 50] as const
const step = ref<number>(10)

// Manual moves need a live, idle machine. The cockpit stays mounted at
// all times and greys out whenever the head can't be driven: no
// connection, a move already in flight, or a job running / paused.
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

async function homeAxis(axis?: 'X' | 'Y' | 'Z'): Promise<void> {
  const confirmed = await confirmAction({
    title: t('confirm.homeTitle'),
    message: t('confirm.homeMsg'),
    confirmLabel: t('plotter.home'),
    cancelLabel: t('confirm.cancel'),
  })
  if (confirmed) plotter.home(job.selectedProfileName, axis)
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
const smallBtn =
  'rounded bg-slate-700 hover:bg-slate-600 px-2 py-1 text-[11px] font-medium text-slate-100 disabled:opacity-40 disabled:cursor-not-allowed'
</script>

<template>
  <div class="space-y-1.5">
    <div class="flex flex-wrap items-start gap-2">
      <!-- X/Y jog cross — ⌂ centre homes all axes -->
      <div class="grid w-[5rem] shrink-0 grid-cols-3 gap-1">
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
          :aria-label="t('plotter.homeAll')"
          :title="t('plotter.homeAll')"
          :disabled="controlsDisabled"
          data-test="home-all"
          @click="homeAxis()"
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

      <!-- Z jog column -->
      <div class="flex flex-col gap-1">
        <span class="text-center text-[10px] uppercase tracking-wider text-slate-500">Z</span>
        <button
          :class="smallBtn"
          :aria-label="t('plotter.jogZUp')"
          :title="t('plotter.jogZUp')"
          :disabled="controlsDisabled"
          data-test="jog-z-up"
          @click="jogZ(1)"
        >
          Z+
        </button>
        <button
          :class="smallBtn"
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
      <div class="flex flex-col gap-1">
        <span class="text-center text-[10px] uppercase tracking-wider text-slate-500">{{
          t('plotter.penControl')
        }}</span>
        <button
          type="button"
          :class="smallBtn"
          :disabled="controlsDisabled || !penUpCmd"
          :title="penUpCmd || t('plotter.penUp')"
          data-test="manual-pen-up"
          @click="penUp"
        >
          ▲
        </button>
        <button
          type="button"
          :class="smallBtn"
          :disabled="controlsDisabled || !penDownCmd"
          :title="penDownCmd || t('plotter.penDown')"
          data-test="manual-pen-down"
          @click="penDown"
        >
          ▼
        </button>
      </div>

      <!-- Per-axis homing -->
      <div class="flex min-w-0 flex-1 flex-col gap-1">
        <span class="text-[10px] uppercase tracking-wider text-slate-500">{{
          t('plotter.homeLabel')
        }}</span>
        <div class="flex gap-1">
          <button
            :class="smallBtn"
            class="flex-1"
            :aria-label="t('plotter.homeX')"
            :title="t('plotter.homeX')"
            :disabled="controlsDisabled"
            data-test="home-x"
            @click="homeAxis('X')"
          >
            ⌂X
          </button>
          <button
            :class="smallBtn"
            class="flex-1"
            :aria-label="t('plotter.homeY')"
            :title="t('plotter.homeY')"
            :disabled="controlsDisabled"
            data-test="home-y"
            @click="homeAxis('Y')"
          >
            ⌂Y
          </button>
          <button
            :class="smallBtn"
            class="flex-1"
            :aria-label="t('plotter.homeZ')"
            :title="t('plotter.homeZ')"
            :disabled="controlsDisabled"
            data-test="home-z"
            @click="homeAxis('Z')"
          >
            ⌂Z
          </button>
        </div>
      </div>
    </div>

    <!-- Shared step size as segmented buttons (X / Y / Z) -->
    <div class="flex items-center gap-1.5">
      <span class="text-[11px] text-slate-400">{{ t('plotter.stepLabel') }}</span>
      <div class="flex gap-1" role="group" :aria-label="t('plotter.stepLabel')">
        <button
          v-for="s in STEPS"
          :key="s"
          type="button"
          class="rounded px-1.5 py-0.5 text-[11px] disabled:opacity-40 disabled:cursor-not-allowed"
          :class="
            step === s
              ? 'bg-emerald-600 text-white'
              : 'bg-slate-700 text-slate-200 hover:bg-slate-600'
          "
          :aria-pressed="step === s"
          :disabled="controlsDisabled"
          :data-test="`step-${s}`"
          @click="step = s"
        >
          {{ s }}
        </button>
      </div>
      <span class="text-[10px] text-slate-500">mm</span>
    </div>
  </div>
</template>
