<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { useUiStore, type EditTab } from '../stores/ui'
import SourceSection from './SourceSection.vue'
import LayoutSection from './LayoutSection.vue'
import LayersSection from './LayersSection.vue'
import GenerateSection from './GenerateSection.vue'

const { t } = useI18n()
const ui = useUiStore()
const store = useJobStore()
const { editModalOpen, editTab } = storeToRefs(ui)

const headerTitle = computed(() => {
  const name = store.lastFile?.name ?? store.job?.source_file ?? null
  return name ? `${t('editModal.title')} — ${name}` : t('editModal.title')
})

const tabs: Array<{ id: EditTab; key: string }> = [
  { id: 'source', key: 'editModal.tabSource' },
  { id: 'layers', key: 'editModal.tabLayers' },
  { id: 'output', key: 'editModal.tabOutput' },
]

// Layers tab is meaningful only when a placement carries layers; the
// output tab needs at least one file ready to optimize/preflight.
const tabAvailable = computed<Record<EditTab, boolean>>(() => ({
  source: true,
  layers: (store.layers?.length ?? 0) > 0,
  output: store.placements.some((p) => p.svg && p.layers.length),
}))

function selectTab(id: EditTab): void {
  if (!tabAvailable.value[id]) return
  editTab.value = id
}

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape' && editModalOpen.value) ui.closeEditModal()
}

// When the active tab becomes unavailable (e.g. user cleared all
// files), bounce back to the source tab so the modal isn't blank.
watch(
  [editModalOpen, () => tabAvailable.value[editTab.value]],
  ([open, available]) => {
    if (open && !available) editTab.value = 'source'
  },
)

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div
    v-if="editModalOpen"
    class="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-4"
    @click.self="ui.closeEditModal()"
  >
    <div
      role="dialog"
      aria-modal="true"
      class="flex h-full max-h-[95vh] w-full max-w-[1600px] flex-col rounded-lg border border-slate-700 bg-slate-900 shadow-2xl"
      :style="{ width: '95vw' }"
    >
      <header class="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <h2 class="truncate text-base font-semibold text-slate-100" :title="headerTitle">
          {{ headerTitle }}
        </h2>
        <button
          type="button"
          class="ml-4 shrink-0 rounded bg-slate-800 px-3 py-1 text-xs text-slate-200 hover:bg-slate-700"
          @click="ui.closeEditModal()"
        >
          {{ t('editModal.done') }}
        </button>
      </header>

      <nav class="flex items-center gap-1 border-b border-slate-700 px-3 py-1.5">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          :disabled="!tabAvailable[tab.id]"
          class="rounded px-3 py-1 text-sm transition"
          :class="editTab === tab.id
            ? 'bg-slate-700 text-white'
            : tabAvailable[tab.id]
              ? 'text-slate-300 hover:bg-slate-800'
              : 'text-slate-600 cursor-not-allowed'"
          @click="selectTab(tab.id)"
        >
          {{ t(tab.key) }}
        </button>
      </nav>

      <main class="flex min-h-0 flex-1 overflow-hidden">
        <div v-if="editTab === 'source'" class="min-h-0 flex-1 overflow-y-auto p-4">
          <SourceSection />
        </div>
        <div v-else-if="editTab === 'layers'" class="min-h-0 flex-1 overflow-y-auto p-4">
          <LayersSection />
        </div>
        <div v-else-if="editTab === 'output'" class="min-h-0 flex-1 overflow-y-auto p-4 space-y-4">
          <LayoutSection />
          <GenerateSection />
        </div>
      </main>
    </div>
  </div>
</template>
