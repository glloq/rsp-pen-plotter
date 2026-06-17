<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useUiStore, type SettingsTab } from '../stores/ui'
import CollapsibleCard from './edit/shared/CollapsibleCard.vue'
import JobHistory from './JobHistory.vue'
import AuditPanel from './AuditPanel.vue'
import ManifestsPanel from './ManifestsPanel.vue'
import SloPanel from './SloPanel.vue'
import SystemPanel from './SystemPanel.vue'
import TimelapseSettings from './TimelapseSettings.vue'

const { t } = useI18n()
const ui = useUiStore()
const { settingsOpen, settingsTab } = storeToRefs(ui)

// Sidebar sections. Diagnostics (audit / slo / manifests) used to be three
// separate top-level tabs; they now live folded under ``advanced`` so the
// modal reads as operator settings first.
const tabs: Array<{ id: SettingsTab; label: string; icon: string }> = [
  { id: 'system', label: 'settings.system', icon: '⚙' },
  { id: 'timelapse', label: 'settings.timelapse', icon: '🎬' },
  { id: 'history', label: 'settings.history', icon: '🕘' },
  { id: 'advanced', label: 'settings.advanced', icon: '🛠' },
]

// Lazy-mount tabs on first visit. The previous ``v-show`` for every tab
// mounted all panels — and fired all their ``onMounted`` API calls — the
// moment the modal opened, even though the operator only sees one at a
// time. The seen-once map keeps an already-visited tab resident so
// switching back is instant (unsaved form state in SystemPanel survives),
// while a never-visited tab pays nothing.
const visited = reactive<Record<SettingsTab, boolean>>({
  system: false,
  timelapse: false,
  history: false,
  advanced: false,
})
function markVisited(tab: SettingsTab): void {
  visited[tab] = true
}
// Mark the initial tab as visited the moment the modal opens so its panel
// mounts in the same tick the modal becomes visible.
watch(
  settingsOpen,
  (open) => {
    if (open) markVisited(settingsTab.value)
  },
  { immediate: true },
)

function select(tab: SettingsTab): void {
  settingsTab.value = tab
  markVisited(tab)
}

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape' && settingsOpen.value) ui.closeSettings()
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div
    v-if="settingsOpen"
    class="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4"
    @click.self="ui.closeSettings()"
  >
    <aside
      role="dialog"
      aria-modal="true"
      class="flex h-full max-h-[88vh] w-full max-w-4xl overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-2xl"
      data-test="settings-modal"
    >
      <!-- SIDEBAR -->
      <nav class="flex w-44 shrink-0 flex-col border-r border-slate-800 bg-slate-950/40">
        <header class="border-b border-slate-800 px-4 py-3">
          <h2 class="text-sm font-semibold text-slate-100">{{ t('settings.title') }}</h2>
        </header>
        <ul class="flex-1 space-y-0.5 p-2">
          <li v-for="tab in tabs" :key="tab.id">
            <button
              type="button"
              class="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm transition"
              :class="
                settingsTab === tab.id
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              "
              :data-test="`settings-tab-${tab.id}`"
              @click="select(tab.id)"
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
            {{ t(tabs.find((tab) => tab.id === settingsTab)?.label ?? 'settings.title') }}
          </h3>
          <button
            type="button"
            class="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            :aria-label="t('settings.close')"
            @click="ui.closeSettings()"
          >
            ✕
          </button>
        </header>

        <div class="min-w-0 flex-1 overflow-y-auto p-4">
          <div v-show="settingsTab === 'system'">
            <SystemPanel v-if="visited.system" />
          </div>
          <div v-show="settingsTab === 'timelapse'">
            <TimelapseSettings v-if="visited.timelapse" />
          </div>
          <div v-show="settingsTab === 'history'">
            <JobHistory v-if="visited.history" />
          </div>
          <div v-show="settingsTab === 'advanced'" class="space-y-3">
            <template v-if="visited.advanced">
              <p class="text-xs text-slate-400">{{ t('settings.advancedHint') }}</p>
              <CollapsibleCard card-key="settings-audit" :title="t('settings.audit')">
                <AuditPanel />
              </CollapsibleCard>
              <CollapsibleCard card-key="settings-slo" :title="t('settings.slo')">
                <SloPanel />
              </CollapsibleCard>
              <CollapsibleCard card-key="settings-manifests" :title="t('settings.manifests')">
                <ManifestsPanel />
              </CollapsibleCard>
            </template>
          </div>
        </div>
      </section>
    </aside>
  </div>
</template>
