<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import type { PrintRun } from '../api/client'
import { confirmAction } from '../composables/confirm'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'
import { useQueueStore } from '../stores/queue'
import { useUiStore, type PlotterTab } from '../stores/ui'
import JogControls from './JogControls.vue'
import ProfileEditor from './ProfileEditor.vue'
import MacroPanel from './MacroPanel.vue'

const { t } = useI18n()
const job = useJobStore()
const plotter = usePlotterStore()
const queue = useQueueStore()
const ui = useUiStore()
const { plotterDrawerOpen, plotterTab } = storeToRefs(ui)
const { status, port, baudrate, terminator, error, progress } = storeToRefs(plotter)

watch(
  // Re-derive the default serial terminator whenever the active profile
  // (or its EBB config) changes. The drawer still lets the operator
  // override it on-the-fly for debugging — we only seed the default here.
  () => [job.selectedProfile?.gcode_dialect, job.selectedProfile?.ebb?.serial_terminator] as const,
  ([dialect, ebbTerminator]) => {
    if (dialect === 'ebb') {
      terminator.value = ebbTerminator ?? 'cr'
    } else {
      terminator.value = 'lf'
    }
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

const tabs: Array<{ id: PlotterTab; label: string; icon: string }> = [
  { id: 'connection', label: 'plotter.tabConnection', icon: '⚡' },
  { id: 'profile', label: 'plotter.tabProfile', icon: '⚙' },
  { id: 'macros', label: 'plotter.tabMacros', icon: '⌘' },
  { id: 'queue', label: 'plotter.tabQueue', icon: '☰' },
]

function selectTab(tab: PlotterTab): void {
  plotterTab.value = tab
}

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
    class="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4"
    @click.self="ui.closePlotterDrawer()"
  >
    <aside
      role="dialog"
      aria-modal="true"
      class="flex h-full max-h-[92vh] w-full max-w-5xl overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-2xl"
    >
      <!-- SIDEBAR -->
      <nav class="flex w-48 shrink-0 flex-col border-r border-slate-800 bg-slate-950/40">
        <header class="border-b border-slate-800 px-4 py-3">
          <h2 class="text-sm font-semibold text-slate-100">{{ t('plotter.title') }}</h2>
          <p class="mt-0.5 flex items-center gap-1.5 text-[11px]">
            <span
              class="inline-block h-1.5 w-1.5 rounded-full"
              :class="status.connected ? 'bg-emerald-400' : 'bg-slate-600'"
            />
            <span :class="status.connected ? 'text-emerald-300' : 'text-slate-500'">
              {{ status.connected ? t('plotter.connected') : t('machine.disconnected') }}
            </span>
          </p>
        </header>
        <ul class="flex-1 space-y-0.5 p-2">
          <li v-for="tab in tabs" :key="tab.id">
            <button
              type="button"
              class="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm transition"
              :class="
                plotterTab === tab.id
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              "
              @click="selectTab(tab.id)"
            >
              <span class="w-4 text-center text-base leading-none">{{ tab.icon }}</span>
              <span>{{ t(tab.label) }}</span>
              <span
                v-if="tab.id === 'queue' && queue.active.length"
                class="ml-auto rounded bg-slate-700 px-1.5 text-[10px] text-slate-200"
                >{{ queue.active.length }}</span
              >
            </button>
          </li>
        </ul>
      </nav>

      <!-- MAIN -->
      <section class="flex min-w-0 flex-1 flex-col">
        <header class="flex items-center justify-between border-b border-slate-800 px-4 py-3">
          <h3 class="text-base font-semibold text-slate-100">
            {{ t(tabs.find((t) => t.id === plotterTab)?.label ?? 'plotter.title') }}
          </h3>
          <button
            type="button"
            class="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            :aria-label="t('settings.close')"
            @click="ui.closePlotterDrawer()"
          >
            ✕
          </button>
        </header>

        <div class="min-w-0 flex-1 overflow-y-auto p-4">
          <!-- CONNECTION TAB -->
          <div v-show="plotterTab === 'connection'" class="space-y-4">
            <p class="text-xs text-slate-400">{{ t('plotter.connectionHint') }}</p>

            <section class="space-y-2">
              <h4 class="px-1 text-xs uppercase tracking-wider text-slate-500">
                {{ t('execute.connection') }}
              </h4>

              <div
                v-if="!status.connected"
                class="space-y-2 rounded-lg border border-slate-700 bg-slate-800 p-3"
              >
                <label class="block text-xs text-slate-400">
                  {{ t('plotter.port') }}
                  <input
                    v-model="port"
                    placeholder="/dev/ttyUSB0"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
                  />
                  <span class="mt-0.5 block text-[11px] text-slate-500">{{
                    t('plotter.portHint')
                  }}</span>
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

              <div
                v-else
                class="flex items-center justify-between rounded-lg border border-emerald-800 bg-emerald-950/30 px-3 py-2 text-sm"
              >
                <span class="text-emerald-300"
                  >● {{ t('plotter.connected') }} · {{ port }} @ {{ baudrate }}</span
                >
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
              <p v-if="status.message" class="mt-0.5 text-sm text-amber-100">
                {{ status.message }}
              </p>
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
              <h4 class="px-1 text-xs uppercase tracking-wider text-slate-500">
                {{ t('execute.jog') }}
              </h4>
              <div class="rounded-lg border border-slate-700 bg-slate-800 p-3">
                <JogControls />
              </div>
            </section>

            <!-- RUNNING -->
            <section
              v-if="status.connected && (status.state === 'running' || status.state === 'paused')"
              class="space-y-2"
            >
              <h4 class="px-1 text-xs uppercase tracking-wider text-slate-500">
                {{ t('execute.run') }}
              </h4>
              <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-2">
                <div class="mb-1 flex justify-between text-[10px] text-slate-500">
                  <span>{{ t(`machine.${status.state}`) }}</span>
                  <span class="font-mono">{{ status.acked }} / {{ status.total }}</span>
                </div>
                <div class="h-1.5 w-full overflow-hidden rounded bg-slate-700">
                  <div class="h-full bg-emerald-500" :style="{ width: `${progress * 100}%` }" />
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
            </section>

            <p
              v-else-if="status.connected && status.state === 'done'"
              class="rounded border border-emerald-800 bg-emerald-950/40 px-2 py-1 text-xs text-emerald-200"
            >
              ✓ {{ t('machine.done') }} · {{ status.acked }} / {{ status.total }}
            </p>
            <p
              v-else-if="
                status.connected && (status.state === 'aborted' || status.state === 'error')
              "
              class="rounded border border-amber-700 bg-amber-950/40 px-2 py-1 text-xs text-amber-200"
            >
              {{ t(`machine.${status.state}`) }}
              <span v-if="status.message"> · {{ status.message }}</span>
            </p>

            <p v-if="error" class="text-xs text-red-400">{{ error }}</p>
          </div>

          <!-- PROFILE TAB -->
          <div v-show="plotterTab === 'profile'">
            <ProfileEditor />
          </div>

          <!-- MACROS TAB -->
          <div v-show="plotterTab === 'macros'" class="space-y-3">
            <p class="text-xs text-slate-400">{{ t('plotter.macrosHint') }}</p>
            <MacroPanel />
          </div>

          <!-- QUEUE TAB -->
          <div v-show="plotterTab === 'queue'" class="space-y-3">
            <p class="text-xs text-slate-400">{{ t('plotter.queueHint') }}</p>

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
                        {{ t(`queue.state.${run.state}`) }} · {{ run.acked_lines }}/{{
                          run.total_lines
                        }}
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
                    <div
                      class="h-full bg-emerald-500"
                      :style="{ width: `${runProgress(run) * 100}%` }"
                    />
                  </div>
                  <p v-if="run.error" class="mt-1 text-[10px] text-red-400">{{ run.error }}</p>
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
        </div>
      </section>
    </aside>
  </div>
</template>
