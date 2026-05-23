<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'
import EditPreviewPane from './edit/EditPreviewPane.vue'
import SourceSection from './SourceSection.vue'
import LayersSection from './LayersSection.vue'

const { t } = useI18n()
const ui = useUiStore()
const store = useJobStore()
const { editModalOpen } = storeToRefs(ui)

const headerTitle = computed(() => {
  const name = store.lastFile?.name ?? store.job?.source_file ?? null
  return name ? `${t('editModal.title')} — ${name}` : t('editModal.title')
})

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape' && editModalOpen.value) ui.closeEditModal()
}

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

      <!-- Split-pane: preview locks to the left at all times, every
           settings card stacks in the scrollable right pane. SourceSection
           owns the preview state and ``provide``s it to EditPreviewPane
           via useEditState — it must therefore be mounted as a sibling
           inside the same parent so the injection key is in scope. -->
      <main class="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(360px,42%)] overflow-hidden">
        <div class="min-h-0 overflow-hidden border-r border-slate-700 bg-slate-950/60">
          <EditPreviewPane />
        </div>
        <div class="min-h-0 space-y-3 overflow-y-auto p-4">
          <SourceSection />
          <LayersSection />
        </div>
      </main>
    </div>
  </div>
</template>
