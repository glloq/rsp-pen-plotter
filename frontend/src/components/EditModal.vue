<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useUiStore } from '../stores/ui'
import PreparePane from './PreparePane.vue'

const { t } = useI18n()
const ui = useUiStore()
const { editModalOpen } = storeToRefs(ui)

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape' && editModalOpen.value) ui.closeEditModal()
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div
    v-if="editModalOpen"
    class="fixed inset-0 z-40 flex items-stretch justify-end bg-black/60"
    @click.self="ui.closeEditModal()"
  >
    <div
      role="dialog"
      aria-modal="true"
      class="flex h-full w-full max-w-lg flex-col border-l border-slate-700 bg-slate-900 shadow-2xl"
    >
      <header class="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <h2 class="text-base font-semibold text-slate-100">{{ t('editModal.title') }}</h2>
        <button
          type="button"
          class="rounded bg-slate-800 px-3 py-1 text-xs text-slate-200 hover:bg-slate-700"
          @click="ui.closeEditModal()"
        >
          {{ t('editModal.done') }}
        </button>
      </header>
      <div class="flex min-h-0 flex-1 overflow-hidden">
        <PreparePane />
      </div>
    </div>
  </div>
</template>
