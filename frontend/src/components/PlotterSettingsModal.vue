<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import type { MachineCapabilities } from '../domain/capability/schemas'
import type { ToolChangeMethod } from '../api/client'
import { useJobStore } from '../stores/job'
import { usePlotterStore } from '../stores/plotter'
import { useToastStore } from '../stores/toasts'
import { useUiStore, type PlotterTab } from '../stores/ui'
import AvailableColorsPanel from './AvailableColorsPanel.vue'
import ProfileEditor from './ProfileEditor.vue'
import MacroPanel from './MacroPanel.vue'
import CapabilityWizard from './v2/CapabilityWizard.vue'

const { t } = useI18n()
const job = useJobStore()
const plotter = usePlotterStore()
const ui = useUiStore()
const { plotterSettingsOpen, plotterTab } = storeToRefs(ui)
const { status, port, baudrate, terminator, error, progress } = storeToRefs(plotter)

watch(
  // The serial terminator follows the active profile so there's a single
  // source of truth: EBB profiles carry their own ``serial_terminator``
  // (default CR), every other dialect uses LF. The connection tab shows
  // this value read-only rather than letting it drift from the profile.
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

const tabs: Array<{ id: PlotterTab; label: string; icon: string }> = [
  { id: 'connection', label: 'plotter.tabConnection', icon: '⚡' },
  { id: 'profile', label: 'plotter.tabProfile', icon: '⚙' },
  { id: 'colors', label: 'plotter.tabColors', icon: '◐' },
  { id: 'macros', label: 'plotter.tabMacros', icon: '⌘' },
]

// Lazy-mount tabs on first visit. Same rationale as SettingsDrawer:
// previously, opening the modal mounted ProfileEditor, AvailableColorsPanel
// AND MacroPanel at the same time even though the operator sees one at a
// time. ProfileEditor in particular instantiates ``useProfileDraft`` and
// clones the active profile on mount — a real cost we don't want to pay
// when the operator only came to load a pen colour. The seen-once map
// keeps already-visited tabs resident so switching back is instant.
const visited = reactive<Record<PlotterTab, boolean>>({
  connection: false,
  profile: false,
  colors: false,
  macros: false,
  queue: false,
})
function markVisited(tab: PlotterTab): void {
  visited[tab] = true
}
watch(
  plotterSettingsOpen,
  (open) => {
    if (open) markVisited(plotterTab.value)
  },
  { immediate: true },
)

function selectTab(tab: PlotterTab): void {
  plotterTab.value = tab
  markVisited(tab)
}

// Capability wizard entrypoint inside the profile tab.
const wizardOpen = ref(false)
const toasts = useToastStore()

function toolChangeMethodFor(mode: MachineCapabilities['tool_change']['mode']): ToolChangeMethod {
  switch (mode) {
    case 'firmware':
      return 'carousel'
    case 'host_macro':
      return 'rack'
    case 'manual':
      return 'manual_pause'
    case 'single_pen':
      return 'none'
  }
}

async function onWizardConfirm(capabilities: MachineCapabilities): Promise<void> {
  const proposed = window.prompt(t('plotter.newPlotterPrompt'), 'Custom plotter')
  if (!proposed || !proposed.trim()) {
    wizardOpen.value = false
    return
  }
  const name = proposed.trim()
  if (job.profiles.some((p) => p.name === name)) {
    toasts.error(t('plotter.newPlotterDuplicate', { name }))
    return
  }
  const base = job.selectedProfile
  if (!base) {
    toasts.error(t('plotter.newPlotterNoBase'))
    return
  }
  // ``tool_change_command`` is mode-dependent (same rule as the
  // ProfilePenFields mode switch): firmware needs a swap trigger the
  // controller understands — inheriting the base profile's ``M0``
  // would feed-hold the machine with no prompt — while every other
  // mode wants the portable ``M0`` pause boundary.
  const mode = capabilities.tool_change.mode
  const baseCmd = (base.tool_change_command ?? '').trim()
  const toolChangeCommand =
    mode === 'firmware' ? (!baseCmd || baseCmd === 'M0' ? 'M6 T{slot}' : baseCmd) : 'M0'
  const next = {
    ...base,
    name,
    tool_change_method: toolChangeMethodFor(mode),
    tool_change_command: toolChangeCommand,
    pen_slot_count: Math.max(1, capabilities.max_pens_in_magazine),
    capabilities,
  }
  try {
    await job.saveProfile(next)
    wizardOpen.value = false
    toasts.success(t('plotter.newPlotterSaved', { name }))
  } catch (err) {
    toasts.critical(
      `${t('plotter.newPlotterFailed')} — ${(err as Error).message ?? 'unknown error'}`,
    )
  }
}

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape' && plotterSettingsOpen.value) ui.closePlotterSettings()
}

onMounted(() => {
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div
    v-if="plotterSettingsOpen"
    class="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4"
    @click.self="ui.closePlotterSettings()"
  >
    <aside
      role="dialog"
      aria-modal="true"
      class="flex h-full max-h-[92vh] w-full max-w-5xl overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-2xl"
    >
      <!-- SIDEBAR -->
      <nav class="flex w-48 shrink-0 flex-col border-r border-slate-800 bg-slate-950/40">
        <header class="border-b border-slate-800 px-4 py-3">
          <h2 class="text-sm font-semibold text-slate-100">{{ t('plotter.settingsTitle') }}</h2>
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
              :data-test="`plotter-tab-${tab.id}`"
              @click="selectTab(tab.id)"
            >
              <span class="w-4 text-center text-base leading-none">{{ tab.icon }}</span>
              <span>{{ t(tab.label) }}</span>
            </button>
          </li>
        </ul>
      </nav>

      <!-- MAIN -->
      <section class="flex min-w-0 flex-1 flex-col">
        <header class="flex items-center justify-between border-b border-slate-800 px-4 py-3">
          <h3 class="text-base font-semibold text-slate-100">
            {{ t(tabs.find((tab) => tab.id === plotterTab)?.label ?? 'plotter.settingsTitle') }}
          </h3>
          <button
            type="button"
            class="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            :aria-label="t('settings.close')"
            @click="ui.closePlotterSettings()"
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
                    <div
                      class="mt-0.5 flex w-full items-center rounded border border-slate-700 bg-slate-800/60 px-2 py-1 text-sm text-slate-300"
                      data-test="terminator-readonly"
                    >
                      <span class="font-mono uppercase">{{ terminator }}</span>
                      <span class="ml-auto text-[10px] text-slate-500">{{
                        t('execute.terminatorFromProfile')
                      }}</span>
                    </div>
                  </label>
                </div>
                <button
                  type="button"
                  class="w-full rounded bg-emerald-600 hover:bg-emerald-500 px-3 py-2 text-sm font-medium text-white"
                  data-test="plotter-connect"
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
          <div v-show="plotterTab === 'profile'" class="space-y-3">
            <template v-if="visited.profile">
              <div class="flex items-center justify-end">
                <button
                  v-if="!wizardOpen"
                  type="button"
                  class="rounded border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700"
                  data-test="open-capability-wizard"
                  @click="wizardOpen = true"
                >
                  + {{ t('plotter.newPlotterWizard') }}
                </button>
              </div>
              <div
                v-if="wizardOpen"
                class="rounded-lg border border-slate-700 bg-slate-800/40 p-3"
                data-test="capability-wizard-host"
              >
                <CapabilityWizard @cancel="wizardOpen = false" @confirm="onWizardConfirm" />
              </div>
              <ProfileEditor />
            </template>
          </div>

          <!-- COLORS TAB -->
          <div v-show="plotterTab === 'colors'" class="space-y-4">
            <AvailableColorsPanel v-if="visited.colors" />
          </div>

          <!-- MACROS TAB -->
          <div v-show="plotterTab === 'macros'" class="space-y-3">
            <template v-if="visited.macros">
              <p class="text-xs text-slate-400">{{ t('plotter.macrosHint') }}</p>
              <MacroPanel />
            </template>
          </div>
        </div>
      </section>
    </aside>
  </div>
</template>
