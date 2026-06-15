<script setup lang="ts">
// Page navigator for multi-page documents (PDF / DOCX / …) in the editor
// modal. Those sources convert one page at a time; the chevrons ask the host
// to re-run the conversion for the chosen page so a whole document can be
// edited without leaving the modal.
//
// Extracted from ``EditModalV2.vue`` (audit P2 — "bloc de navigation
// document/page") as a pure presentational component: it owns no state, just
// renders the current/total label and emits ``go`` with the requested
// 0-based page index. The host keeps the ``goToPage`` wiring + the
// ``v-if="hasPages"`` gate.
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  /** 0-based index of the page currently being edited. */
  currentPage: number
  /** Total page count of the source document. */
  pageCount: number
}>()

const emit = defineEmits<{ (e: 'go', page: number): void }>()

const { t } = useI18n()
</script>

<template>
  <div class="modal-v2__pages" data-test="modal-v2-pages">
    <button
      type="button"
      class="modal-v2__page-btn"
      :disabled="props.currentPage <= 0"
      :aria-label="t('v2.modal.pagePrev')"
      :title="t('v2.modal.pagePrev')"
      data-test="modal-v2-page-prev"
      @click="emit('go', props.currentPage - 1)"
    >
      ‹
    </button>
    <span class="modal-v2__page-label" data-test="modal-v2-page-label">
      {{ t('upload.pageOf', { current: props.currentPage + 1, total: props.pageCount }) }}
    </span>
    <button
      type="button"
      class="modal-v2__page-btn"
      :disabled="props.currentPage >= props.pageCount - 1"
      :aria-label="t('v2.modal.pageNext')"
      :title="t('v2.modal.pageNext')"
      data-test="modal-v2-page-next"
      @click="emit('go', props.currentPage + 1)"
    >
      ›
    </button>
  </div>
</template>

<style scoped>
.modal-v2__pages {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0;
}
.modal-v2__page-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.6rem;
  height: 1.6rem;
  border: 1px solid #334155;
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 4px;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
}
.modal-v2__page-btn:hover:not(:disabled) {
  background: #334155;
}
.modal-v2__page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.modal-v2__page-btn:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.modal-v2__page-label {
  font-size: 0.75rem;
  color: #cbd5e1;
  font-variant-numeric: tabular-nums;
}
</style>
