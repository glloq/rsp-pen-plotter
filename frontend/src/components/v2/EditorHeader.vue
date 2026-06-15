<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AssistantModeToggle from '../AssistantModeToggle.vue'
import SheetPicker from './SheetPicker.vue'

// Presentational header for the editor modal. The dialog keeps its
// accessible name via the parent's ``aria-label`` (no visible title, per
// operator feedback). Three zones, left→right:
//   - LEFT   : the sheet-format picker, sitting directly above the preview
//     so the operator sizes the page before reading the result.
//   - CENTER : the assisted/expert UX-mode toggle.
//   - RIGHT  : the single "save the print style" commit button and the
//     close button.
// The status/preflight chips (file / machine / sheet / inks) and the cost
// estimates were removed from here to give the preview maximum room.
defineProps<{
  hasPlacement: boolean
  /** Disables the save button (no decision / no placement / busy). */
  saveDisabled: boolean
}>()

const emit = defineEmits<{ (e: 'close'): void; (e: 'save'): void }>()

const { t } = useI18n()
</script>

<template>
  <header class="modal-v2__header">
    <!-- LEFT: sheet-format picker, above the preview. -->
    <div class="modal-v2__header-left">
      <SheetPicker v-if="hasPlacement" />
    </div>

    <!-- CENTER: assisted / expert UX-mode selector. -->
    <div class="modal-v2__header-center">
      <AssistantModeToggle />
    </div>

    <!-- RIGHT: the single commit button + close. -->
    <div class="modal-v2__header-right">
      <button
        type="button"
        class="modal-v2__save"
        :disabled="saveDisabled"
        :title="!hasPlacement ? t('v2.modal.noPlacement') : t('v2.modal.saveStyleHint')"
        data-test="confirm-button"
        @click="emit('save')"
      >
        {{ t('v2.modal.saveStyle') }}
      </button>
      <button
        type="button"
        class="close"
        :aria-label="t('settings.close')"
        data-test="modal-v2-close"
        @click="emit('close')"
      >
        ×
      </button>
    </div>
  </header>
</template>

<style scoped>
.modal-v2__header {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid #334155;
}
.modal-v2__header-left {
  min-width: 0;
}
.modal-v2__header-center {
  display: flex;
  justify-content: center;
}
.modal-v2__header-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.6rem;
}
.modal-v2__save {
  padding: 0.5rem 1.3rem;
  border: 1px solid #059669;
  background: #059669;
  color: white;
  border-radius: 4px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition:
    background 0.12s ease,
    transform 0.08s ease;
}
.modal-v2__save:hover:not(:disabled) {
  background: #10b981;
}
.modal-v2__save:active:not(:disabled) {
  transform: scale(0.97);
}
.modal-v2__save:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.modal-v2__save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.close {
  border: none;
  background: transparent;
  font-size: 1.5rem;
  cursor: pointer;
  color: #94a3b8;
  line-height: 1;
}
.close:hover {
  color: #e2e8f0;
}

/* On narrow viewports the three-zone grid collapses to a wrapping row so
   the picker, toggle and buttons stay reachable on a tablet. */
@media (max-width: 900px) {
  .modal-v2__header {
    grid-template-columns: 1fr;
    gap: 0.5rem;
  }
  .modal-v2__header-center {
    justify-content: flex-start;
  }
  .modal-v2__header-right {
    justify-content: flex-start;
  }
}
</style>
