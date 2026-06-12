<script setup lang="ts">
// Print queue + live-run cockpit for the main-page print follow-up.
//
// Lifted out of the Plotter settings modal: the queue is part of "track
// the print", not "configure the machine", so it belongs next to the
// manual controls on the main page rather than buried in a settings tab.
//
// Drives the canonical queue lifecycle (enqueue / pause / resume /
// cancel / delete) plus the one-shot "send now" direct serial path,
// mirroring the header transport. Stays in sync via the queue store's
// polling (started in App.vue).

import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import type { PrintRun } from '../api/client'
import { confirmAction } from '../composables/confirm'
import { ensureMagazineLoaded } from '../composables/magazineGate'
import { useAvailableColorsStore } from '../stores/availableColors'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'
import { useQueueStore } from '../stores/queue'
import RunActionsPanel from './v2/RunActionsPanel.vue'
import RunTimeline from './v2/RunTimeline.vue'

const { t } = useI18n()
const job = useJobStore()
const plotter = usePlotterStore()
const queue = useQueueStore()
const availableColors = useAvailableColorsStore()
const { status } = storeToRefs(plotter)

const stateClass: Record<PrintRun['state'], string> = {
  queued: 'text-slate-300',
  running: 'text-emerald-300',
  paused: 'text-amber-300',
  completed: 'text-sky-300',
  failed: 'text-red-400',
  canceled: 'text-slate-500',
}

const canSend = computed(() => Boolean(job.gcode))

function runProgress(run: PrintRun): number {
  return run.total_lines > 0 ? run.acked_lines / run.total_lines : 0
}

function logOdometerForCurrentJob(): void {
  for (const [hex, mm] of Object.entries(job.lengthMmByColor)) {
    void availableColors.addToOdometer(hex, mm)
  }
}

async function sendNow(): Promise<void> {
  if (!job.gcode) return
  // Magazine gate first (multi-pen multicolour jobs): the modal asks
  // to load the planned inks and carries its own launch button; the
  // generic confirm only runs when the gate was skipped.
  const gate = await ensureMagazineLoaded()
  if (gate === 'cancelled') return
  if (gate === 'skipped') {
    const confirmed = await confirmAction({
      title: t('confirm.sendJobTitle'),
      message: t('confirm.sendJobMsg'),
      confirmLabel: t('plotter.sendJob'),
      cancelLabel: t('confirm.cancel'),
    })
    if (!confirmed) return
  }
  if (!job.gcode) return
  logOdometerForCurrentJob()
  void plotter.run(job.gcode)
}

async function enqueue(): Promise<void> {
  if (!job.gcode) return
  // Same gate as the direct send: a queued run will pause on the same
  // swap prompts, so the magazine must match the plan before enqueue.
  const gate = await ensureMagazineLoaded()
  if (gate === 'cancelled') return
  if (!job.gcode) return
  logOdometerForCurrentJob()
  const name = job.job?.source_file ?? 'job'
  await queue.enqueue(name, job.selectedProfileName, job.gcode)
}

async function cancelRun(run: PrintRun): Promise<void> {
  const confirmed = await confirmAction({
    title: t('queue.cancelTitle'),
    message: t('queue.cancelMsg', { name: run.name }),
    confirmLabel: t('queue.cancel'),
    cancelLabel: t('confirm.cancel'),
    danger: true,
  })
  if (confirmed) await queue.act(run.id, 'cancel')
}

// Active run cockpit (single live run), kept in sync via queue polling.
const activeRun = computed(() => queue.active[0] ?? null)

async function activePause(): Promise<void> {
  if (activeRun.value) await queue.act(activeRun.value.id, 'pause')
}
async function activeResume(): Promise<void> {
  if (activeRun.value) await queue.act(activeRun.value.id, 'resume')
}
async function activeCancel(): Promise<void> {
  if (activeRun.value) await queue.act(activeRun.value.id, 'cancel')
}
</script>

<template>
  <div class="space-y-3" data-test="print-queue-panel">
    <section
      v-if="activeRun"
      class="space-y-2 rounded-lg border border-slate-700 bg-slate-800/40 p-3"
      data-test="active-run-cockpit"
    >
      <RunTimeline :run="activeRun" />
      <RunActionsPanel
        :run="activeRun"
        :next-action-hint="activeRun.swap_prompt ?? null"
        @pause="activePause"
        @resume="activeResume"
        @cancel="activeCancel"
      />
    </section>

    <section class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2">
      <p v-if="!canSend" class="text-xs text-slate-500">{{ t('execute.runHint') }}</p>

      <div v-if="status.connected && canSend" class="flex gap-2">
        <button
          class="flex-1 rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
          :disabled="!canSend"
          @click="sendNow"
        >
          ▶ {{ t('plotter.sendJob') }}
        </button>
        <button
          class="rounded bg-sky-600 hover:bg-sky-500 px-3 py-2 text-sm text-white disabled:opacity-50"
          :disabled="!canSend"
          :title="t('queue.add')"
          @click="enqueue"
        >
          + {{ t('execute.queue') }}
        </button>
      </div>

      <button
        v-else-if="!status.connected && canSend"
        class="w-full rounded bg-sky-600 hover:bg-sky-500 px-3 py-2 text-sm font-medium text-white"
        @click="enqueue"
      >
        + {{ t('queue.add') }}
      </button>
    </section>

    <section v-if="queue.runs.length" class="space-y-2">
      <h4 class="px-1 text-xs uppercase tracking-wider text-slate-500">
        {{ t('queue.title') }}
        <span class="ml-1 rounded bg-slate-700 px-1.5 text-[10px] text-slate-300">{{
          queue.active.length
        }}</span>
      </h4>

      <div class="space-y-1.5">
        <div
          v-for="run in queue.runs"
          :key="run.id"
          class="rounded-lg border border-slate-700 bg-slate-800/60 px-2.5 py-1.5"
        >
          <div class="flex items-center gap-2">
            <div class="min-w-0 flex-1">
              <p class="truncate text-xs font-medium text-slate-200" :title="run.name">
                {{ run.name }}
              </p>
              <p class="text-[10px]" :class="stateClass[run.state]">
                {{ t(`queue.state.${run.state}`) }} · {{ run.acked_lines }}/{{ run.total_lines }}
              </p>
            </div>
            <button
              v-if="run.state === 'running'"
              class="rounded bg-slate-700 px-1.5 py-0.5 text-[10px] text-slate-100 hover:bg-slate-600"
              @click="queue.act(run.id, 'pause')"
            >
              ‖
            </button>
            <button
              v-if="run.state === 'paused'"
              class="rounded bg-emerald-600 px-1.5 py-0.5 text-[10px] text-white hover:bg-emerald-500"
              @click="queue.act(run.id, 'resume')"
            >
              ▶
            </button>
            <button
              v-if="['queued', 'running', 'paused'].includes(run.state)"
              class="rounded bg-red-900/70 px-1.5 py-0.5 text-[10px] text-red-200 hover:bg-red-800"
              @click="cancelRun(run)"
            >
              ✕
            </button>
            <button
              v-else
              class="rounded bg-slate-700 px-1.5 py-0.5 text-[10px] text-slate-300 hover:bg-slate-600"
              :aria-label="t('queue.delete')"
              @click="queue.remove(run.id)"
            >
              ×
            </button>
          </div>
          <div
            v-if="run.state === 'running' || run.state === 'paused'"
            class="mt-1 h-0.5 w-full overflow-hidden rounded bg-slate-700"
          >
            <div class="h-full bg-emerald-500" :style="{ width: `${runProgress(run) * 100}%` }" />
          </div>
          <p v-if="run.error" class="mt-1 text-[10px] text-red-400">{{ run.error }}</p>
          <div
            v-if="run.skipped_layers && run.skipped_layers.length"
            class="mt-1"
            :data-test="`run-skipped-${run.id}`"
          >
            <span
              class="rounded bg-amber-900/60 px-1.5 py-0.5 text-[10px] font-medium text-amber-200"
              :title="(run.skipped_layers ?? []).join(', ')"
            >
              ⚠ {{ t('queue.skippedBadge', { count: run.skipped_layers.length }) }}
            </span>
          </div>
        </div>
      </div>

      <p v-if="queue.error" class="text-[10px] text-red-400">{{ queue.error }}</p>
    </section>

    <p
      v-else
      class="rounded-lg border border-dashed border-slate-700 px-3 py-4 text-center text-xs text-slate-500"
    >
      {{ t('queue.empty') }}
    </p>
  </div>
</template>
