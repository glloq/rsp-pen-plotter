<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import type { PrintRun } from '../api/client'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'
import { useQueueStore } from '../stores/queue'
import { useUiStore } from '../stores/ui'
import JogControls from './JogControls.vue'

const { t } = useI18n()
const job = useJobStore()
const plotter = usePlotterStore()
const queue = useQueueStore()
const ui = useUiStore()
const { plotterDrawerOpen } = storeToRefs(ui)
const { status, port, baudrate, terminator, error, progress } = storeToRefs(plotter)

watch(
  () => job.selectedProfile?.gcode_dialect,
  (dialect) => {
    terminator.value = dialect === 'ebb' ? 'cr' : 'lf'
  },
  { immediate: true },
)

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

async function sendNow(): Promise<void> {
  if (!job.gcode) return
  const confirmed = await confirmAction({
    title: t('confirm.sendJobTitle'),
    message: t('confirm.sendJobMsg'),
    confirmLabel: t('plotter.sendJob'),
    cancelLabel: t('confirm.cancel'),
  })
  if (confirmed) plotter.run(job.gcode)
}

async function enqueue(): Promise<void> {
  if (!job.gcode) return
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

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape' && plotterDrawerOpen.value) ui.closePlotterDrawer()
}

onMounted(() => {
  queue.startPolling()
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  queue.stopPolling()
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div
    v-if="plotterDrawerOpen"
    class="fixed inset-0 z-40 flex justify-end bg-black/50"
    @click.self="ui.closePlotterDrawer()"
  >
    <aside
      role="dialog"
      aria-modal="true"
      class="flex h-full w-full max-w-md flex-col border-l border-slate-700 bg-slate-900 shadow-2xl"
    >
      <header class="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <h2 class="text-base font-semibold text-slate-100">{{ t('plotter.title') }}</h2>
        <button
          type="button"
          class="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          :aria-label="t('settings.close')"
          @click="ui.closePlotterDrawer()"
        >
          ✕
        </button>
      </header>

      <div class="flex-1 space-y-4 overflow-y-auto p-3">
        <!-- CONNECTION -->
        <section class="space-y-2">
          <h3 class="px-1 text-xs uppercase tracking-wider text-slate-500">{{ t('execute.connection') }}</h3>

          <div v-if="!status.connected" class="space-y-2 rounded-lg border border-slate-700 bg-slate-800 p-3">
            <label class="block text-xs text-slate-400">
              {{ t('plotter.port') }}
              <input
                v-model="port"
                placeholder="/dev/ttyUSB0"
                class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
              />
            </label>
            <div class="grid grid-cols-2 gap-2">
              <label class="block text-xs text-slate-400">
                {{ t('plotter.baudrate') }}
                <input
                  v-model.number="baudrate"
                  type="number"
                  placeholder="115200"
                  class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                />
              </label>
              <label class="block text-xs text-slate-400">
                {{ t('execute.terminator') }}
                <select
                  v-model="terminator"
                  class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                >
                  <option value="lf">LF</option>
                  <option value="cr">CR</option>
                  <option value="crlf">CRLF</option>
                </select>
              </label>
            </div>
            <button
              type="button"
              class="w-full rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-2 text-sm font-medium text-white"
              @click="plotter.connect()"
            >
              {{ t('plotter.connect') }}
            </button>
          </div>

          <div v-else class="flex items-center justify-between rounded-lg border border-emerald-800 bg-emerald-950/30 px-3 py-2 text-sm">
            <span class="text-emerald-300">● {{ t('plotter.connected') }}</span>
            <button
              class="text-xs text-slate-400 hover:text-slate-200"
              @click="plotter.disconnect()"
            >
              {{ t('plotter.disconnect') }}
            </button>
          </div>
        </section>

        <!-- TOOL CHANGE -->
        <section
          v-if="status.connected && status.state === 'waiting'"
          class="rounded-lg border border-amber-600 bg-amber-950/40 p-3"
        >
          <p class="text-sm font-medium text-amber-200">{{ t('plotter.toolChange') }}</p>
          <p v-if="status.message" class="mt-0.5 text-sm text-amber-100">{{ status.message }}</p>
          <button
            type="button"
            class="mt-2 w-full rounded bg-amber-600 px-3 py-2 text-sm font-medium text-white hover:bg-amber-500"
            @click="plotter.resume()"
          >
            {{ t('plotter.continue') }}
          </button>
        </section>

        <!-- JOG -->
        <section v-if="status.connected" class="space-y-2">
          <h3 class="px-1 text-xs uppercase tracking-wider text-slate-500">{{ t('execute.jog') }}</h3>
          <div class="rounded-lg border border-slate-700 bg-slate-800 p-3">
            <JogControls />
          </div>
        </section>

        <!-- SEND / QUEUE -->
        <section class="space-y-2">
          <h3 class="px-1 text-xs uppercase tracking-wider text-slate-500">{{ t('execute.run') }}</h3>

          <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2">
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

            <div v-if="status.connected && (status.state === 'running' || status.state === 'paused')" class="space-y-2">
              <div>
                <div class="mb-1 flex justify-between text-[10px] text-slate-500">
                  <span>{{ t(`machine.${status.state}`) }}</span>
                  <span class="font-mono">{{ status.acked }} / {{ status.total }}</span>
                </div>
                <div class="h-1.5 w-full overflow-hidden rounded bg-slate-700">
                  <div class="h-full bg-emerald-500" :style="{ width: `${progress * 100}%` }" />
                </div>
              </div>
              <div class="flex gap-1">
                <button
                  v-if="status.state === 'running'"
                  class="flex-1 rounded bg-slate-700 px-2 py-1 text-xs text-slate-100 hover:bg-slate-600"
                  @click="plotter.pause()"
                >
                  {{ t('plotter.pause') }}
                </button>
                <button
                  v-if="status.state === 'paused'"
                  class="flex-1 rounded bg-emerald-600 px-2 py-1 text-xs text-white hover:bg-emerald-500"
                  @click="plotter.resume()"
                >
                  {{ t('plotter.resume') }}
                </button>
                <button
                  class="flex-1 rounded bg-red-800 px-2 py-1 text-xs text-white hover:bg-red-700"
                  @click="plotter.abort()"
                >
                  {{ t('plotter.abort') }}
                </button>
              </div>
            </div>

            <p
              v-else-if="status.connected && status.state === 'done'"
              class="rounded border border-emerald-800 bg-emerald-950/40 px-2 py-1 text-xs text-emerald-200"
            >
              ✓ {{ t('machine.done') }} · {{ status.acked }} / {{ status.total }}
            </p>
            <p
              v-else-if="status.connected && (status.state === 'aborted' || status.state === 'error')"
              class="rounded border border-amber-700 bg-amber-950/40 px-2 py-1 text-xs text-amber-200"
            >
              {{ t(`machine.${status.state}`) }}
              <span v-if="status.message"> · {{ status.message }}</span>
            </p>

            <p v-if="error" class="text-xs text-red-400">{{ error }}</p>
          </div>
        </section>

        <!-- QUEUE -->
        <section v-if="queue.runs.length" class="space-y-2">
          <h3 class="px-1 text-xs uppercase tracking-wider text-slate-500">
            {{ t('queue.title') }}
            <span class="ml-1 rounded bg-slate-700 px-1.5 text-[10px] text-slate-300">{{ queue.active.length }}</span>
          </h3>

          <div class="space-y-1.5">
            <div
              v-for="run in queue.runs"
              :key="run.id"
              class="rounded-lg border border-slate-700 bg-slate-800/60 px-2.5 py-1.5"
            >
              <div class="flex items-center gap-2">
                <div class="min-w-0 flex-1">
                  <p class="truncate text-xs font-medium text-slate-200" :title="run.name">{{ run.name }}</p>
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
            </div>
          </div>

          <p v-if="queue.error" class="text-[10px] text-red-400">{{ queue.error }}</p>
        </section>
      </div>
    </aside>
  </div>
</template>
