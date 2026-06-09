<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useUiStore, type SettingsTab } from '../stores/ui'
import JobHistory from './JobHistory.vue'
import AuditPanel from './AuditPanel.vue'
import ManifestsPanel from './ManifestsPanel.vue'
import SloPanel from './SloPanel.vue'
import SystemPanel from './SystemPanel.vue'

const { t } = useI18n()
const ui = useUiStore()
const { settingsOpen, settingsTab } = storeToRefs(ui)

const tabs: Array<{ id: SettingsTab; label: string }> = [
  { id: 'system', label: 'settings.system' },
  { id: 'history', label: 'settings.history' },
  { id: 'audit', label: 'settings.audit' },
  { id: 'slo', label: 'settings.slo' },
  { id: 'manifests', label: 'settings.manifests' },
]

// Lazy-mount tabs on first visit. The previous ``v-show`` for every
// tab mounted all five panels — and fired all five ``onMounted`` API
// calls — the moment the drawer opened, even though the operator only
// sees one at a time. The seen-once map keeps an already-visited tab
// resident so switching back is instant (and unsaved form state in
// SystemPanel / ProfileEditor survives), while a never-visited tab
// pays nothing.
const visited = reactive<Record<SettingsTab, boolean>>({
  system: false,
  history: false,
  audit: false,
  slo: false,
  manifests: false,
})
function markVisited(tab: SettingsTab): void {
  visited[tab] = true
}
// Mark the initial tab as visited the moment the drawer opens so its
// panel mounts in the same tick the drawer becomes visible.
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
    class="fixed inset-0 z-40 flex justify-end bg-black/50"
    @click.self="ui.closeSettings()"
  >
    <div
      role="dialog"
      aria-modal="true"
      class="flex h-full w-full max-w-md flex-col border-l border-slate-700 bg-slate-900 shadow-2xl"
    >
      <header class="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <h2 class="text-base font-semibold text-slate-100">{{ t('settings.title') }}</h2>
        <button
          type="button"
          class="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          :aria-label="t('settings.close')"
          @click="ui.closeSettings()"
        >
          ✕
        </button>
      </header>

      <nav class="flex gap-1 border-b border-slate-800 bg-slate-900 px-2 py-1.5">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="rounded px-3 py-1 text-xs transition"
          :class="
            settingsTab === tab.id
              ? 'bg-slate-700 text-white'
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
          "
          @click="select(tab.id)"
        >
          {{ t(tab.label) }}
        </button>
      </nav>

      <div class="flex-1 overflow-y-auto p-4">
        <div v-show="settingsTab === 'system'">
          <SystemPanel v-if="visited.system" />
        </div>
        <div v-show="settingsTab === 'history'">
          <JobHistory v-if="visited.history" />
        </div>
        <div v-show="settingsTab === 'audit'">
          <AuditPanel v-if="visited.audit" />
        </div>
        <div v-show="settingsTab === 'slo'">
          <SloPanel v-if="visited.slo" />
        </div>
        <div v-show="settingsTab === 'manifests'">
          <ManifestsPanel v-if="visited.manifests" />
        </div>
      </div>
    </div>
  </div>
</template>
