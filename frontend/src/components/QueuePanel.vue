<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PrintRun } from '../api/client'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'
import { useQueueStore } from '../stores/queue'

const { t } = useI18n()
const queue = useQueueStore()
const job = useJobStore()
const open = ref(false)

const stateClass: Record<PrintRun['state'], string> = {
  queued: 'text-slate-300',
  running: 'text-emerald-300',
  paused: 'text-amber-300',
  completed: 'text-sky-300',
  failed: 'text-red-400',
  canceled: 'text-slate-500',
}

const canEnqueue = computed(() => Boolean(job.gcode))

function progress(run: PrintRun): number {
  return run.total_lines > 0 ? run.acked_lines / run.total_lines : 0
}

async function addCurrent(): Promise<void> {
  if (!job.gcode) return
  const name = job.job?.source_file ?? 'job'
  await queue.enqueue(name, job.selectedProfileName, job.gcode)
}

async function cancel(run: PrintRun): Promise<void> {
  const confirmed = await confirmAction({
    title: t('queue.cancelTitle'),
    message: t('queue.cancelMsg', { name: run.name }),
    confirmLabel: t('queue.cancel'),
    cancelLabel: t('confirm.cancel'),
    danger: true,
  })
  if (confirmed) await queue.act(run.id, 'cancel')
}

onMounted(() => queue.startPolling())
onBeforeUnmount(() => queue.stopPolling())
</script>

<template>
  <div class="rounded-lg border border-slate-700 bg-slate-800">
    <button
      type="button"
      class="flex w-full items-center justify-between px-4 py-3 text-sm uppercase tracking-wide text-slate-300"
      :aria-expanded="open"
      @click="open = !open"
    >
      {{ t('queue.title') }}
      <span class="flex items-center gap-2">
        <span v-if="queue.active.length" class="rounded bg-slate-700 px-1.5 text-xs text-slate-200">
          {{ queue.active.length }}
        </span>
        <span class="text-slate-500">{{ open ? '−' : '+' }}</span>
      </span>
    </button>

    <div v-if="open" class="space-y-3 border-t border-slate-700 p-4 text-sm">
      <button
        type="button"
        class="w-full rounded bg-sky-600 px-3 py-2 font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        :disabled="!canEnqueue"
        :title="canEnqueue ? '' : t('queue.addHint')"
        @click="addCurrent"
      >
        {{ t('queue.add') }}
      </button>

      <p v-if="!queue.runs.length" class="text-slate-500">{{ t('queue.empty') }}</p>

      <div
        v-for="run in queue.runs"
        :key="run.id"
        class="rounded border border-slate-700 bg-slate-900/50 px-3 py-2"
      >
        <div class="flex items-center gap-2">
          <div class="min-w-0 flex-1">
            <p class="truncate font-medium text-slate-200">{{ run.name }}</p>
            <p class="text-xs" :class="stateClass[run.state]">
              {{ t(`queue.state.${run.state}`) }} · {{ run.acked_lines }}/{{ run.total_lines }}
            </p>
          </div>
          <button
            v-if="run.state === 'running'"
            class="rounded bg-slate-700 px-2 py-1 text-xs text-slate-100 hover:bg-slate-600"
            @click="queue.act(run.id, 'pause')"
          >
            {{ t('queue.pause') }}
          </button>
          <button
            v-if="run.state === 'paused'"
            class="rounded bg-emerald-600 px-2 py-1 text-xs text-white hover:bg-emerald-500"
            @click="queue.act(run.id, 'resume')"
          >
            {{ t('queue.resume') }}
          </button>
          <button
            v-if="['queued', 'running', 'paused'].includes(run.state)"
            class="rounded bg-red-900/70 px-2 py-1 text-xs text-red-200 hover:bg-red-800"
            @click="cancel(run)"
          >
            {{ t('queue.cancel') }}
          </button>
          <button
            v-else
            class="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
            :aria-label="t('queue.delete')"
            :title="t('queue.delete')"
            @click="queue.remove(run.id)"
          >
            ×
          </button>
        </div>
        <div v-if="run.state === 'running' || run.state === 'paused'" class="mt-1 h-1 w-full overflow-hidden rounded bg-slate-700">
          <div class="h-full bg-emerald-500" :style="{ width: `${progress(run) * 100}%` }" />
        </div>
        <p v-if="run.error" class="mt-1 text-xs text-red-400">{{ run.error }}</p>
      </div>

      <p v-if="queue.error" class="text-xs text-red-400">{{ queue.error }}</p>
    </div>
  </div>
</template>
