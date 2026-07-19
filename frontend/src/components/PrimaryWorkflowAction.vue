<script setup lang="ts">
// The single contextual primary action (UX audit vague 2).
//
// One bar, always in the same spot (bottom of the canvas column),
// showing exactly one primary button whose label follows the workflow
// step derived by ``useWorkflowStep``. During a run it becomes
// Pause/Resume with Stop as the destructive secondary — the header
// transport stays untouched (decision record: thumb-distance to Stop
// must not depend on which surface the operator happens to be on).

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { confirmAction } from '../composables/confirm'
import { useLaunchCurrentJob } from '../composables/useLaunchCurrentJob'
import { useWorkflowStep, type WorkflowStep } from '../composables/useWorkflowStep'
import { useJobStore } from '../stores/job'
import { useLibraryStore } from '../stores/library'
import { usePlotterStore } from '../stores/plotter'
import { useQueueStore } from '../stores/queue'
import { useUiStore } from '../stores/ui'

const { t } = useI18n()
const job = useJobStore()
const library = useLibraryStore()
const plotter = usePlotterStore()
const queue = useQueueStore()
const ui = useUiStore()
const { step } = useWorkflowStep()
const { launch } = useLaunchCurrentJob()

const activeRun = computed(() => queue.active[0] ?? null)

const LABELS: Record<WorkflowStep, { label: string; hint: string }> = {
  empty: { label: 'workflow.addFile', hint: 'workflow.hintAddFile' },
  imported: { label: 'workflow.addToPlan', hint: 'workflow.hintAddToPlan' },
  placed: { label: 'workflow.chooseStyle', hint: 'workflow.hintChooseStyle' },
  preflight_blocked: { label: 'workflow.fixPens', hint: 'workflow.hintFixPens' },
  configured: { label: 'workflow.verify', hint: 'workflow.hintVerify' },
  ready_disconnected: { label: 'workflow.connect', hint: 'workflow.hintConnect' },
  ready: { label: 'workflow.launch', hint: 'workflow.hintLaunch' },
  running: { label: 'workflow.pause', hint: 'workflow.hintRunning' },
  paused: { label: 'workflow.resume', hint: 'workflow.hintPaused' },
}

const primaryLabel = computed(() => t(LABELS[step.value].label))
const hint = computed(() => t(LABELS[step.value].hint))

// One in-flight action at a time — the step usually changes as a
// result, and a double-click must not fire the old action twice.
const busy = ref(false)

async function onPrimary(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    await dispatch(step.value)
  } finally {
    busy.value = false
  }
}

async function dispatch(current: WorkflowStep): Promise<void> {
  switch (current) {
    case 'empty':
      // FilesPane owns the hidden <input type=file>; ask it to open.
      ui.requestAddFile()
      return
    case 'imported': {
      // Deterministic pick: the most recently imported file — right
      // after an upload that's exactly the file the operator means.
      const latest = [...library.files].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
      if (!latest) return
      const id = await job.createPlacementFromLibrary(latest.file_id)
      if (id) {
        job.selectPlacement(id)
        ui.canvasTab = 'sheet'
      }
      return
    }
    case 'placed': {
      const target = job.visiblePlacements.find((p) => !p.svg || !p.layers.length)
      if (target) {
        job.selectPlacement(target.id)
        ui.openEditModal()
      }
      return
    }
    case 'preflight_blocked':
      ui.openPlotterSettings('colors')
      return
    case 'configured':
      await job.generate()
      if (job.gcode) {
        ui.canvasTab = job.selectedProfile?.gcode_dialect === 'ebb' ? 'plotter' : 'simulator'
      }
      return
    case 'ready_disconnected':
      await plotter.detectAndConnect()
      // Detection toasts its own failure; fall back to the manual form
      // so the operator isn't left without a next step.
      if (!plotter.status.connected) ui.openPlotterSettings('connection')
      return
    case 'ready':
      await launch()
      return
    case 'running': {
      const run = activeRun.value
      if (run) await queue.act(run.id, 'pause')
      else await plotter.pause()
      return
    }
    case 'paused': {
      const run = activeRun.value
      if (run) await queue.act(run.id, 'resume')
      else await plotter.resume()
      return
    }
  }
}

const showStop = computed(() => step.value === 'running' || step.value === 'paused')

async function onStop(): Promise<void> {
  const run = activeRun.value
  const confirmed = await confirmAction({
    title: t('plotter.stopTitle'),
    message: t('plotter.stopMsg'),
    confirmLabel: t('plotter.abort'),
    cancelLabel: t('confirm.cancel'),
    danger: true,
  })
  if (!confirmed) return
  if (run) await queue.act(run.id, 'cancel')
  else await plotter.abort()
}
</script>

<template>
  <div
    class="flex items-center justify-between gap-3 border-t border-slate-700 bg-slate-900/80 px-3 py-2"
    data-test="primary-workflow"
  >
    <p class="min-w-0 truncate text-xs text-slate-400" data-test="workflow-hint">{{ hint }}</p>
    <div class="flex shrink-0 items-center gap-2">
      <button
        v-if="showStop"
        type="button"
        class="rounded border border-red-900/70 px-3 py-1.5 text-xs text-red-300 hover:bg-red-900/30"
        data-test="workflow-stop"
        @click="onStop"
      >
        ■ {{ t('plotter.stop') }}
      </button>
      <button
        type="button"
        class="rounded bg-emerald-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="busy || job.generating"
        data-test="workflow-primary"
        @click="onPrimary"
      >
        {{ primaryLabel }}
      </button>
    </div>
  </div>
</template>
