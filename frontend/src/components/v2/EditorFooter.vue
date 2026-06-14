<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

// Presentational footer for the editor modal: Cancel, the assisted→expert
// link / expert "Appliquer" commit button, and Generate, plus the inline
// apply-error. All state arrives via props and every action is emitted —
// the parent owns the wiring (see EditModalV2.vue).
const props = defineProps<{
  /** Reason the last expert apply failed, shown inline. Null = hidden. */
  applyError: string | null
  isAssisted: boolean
  isExpert: boolean
  /** Expert draft has uncommitted mutations — drives Apply enable + dot. */
  isDirty: boolean
  hasPlacement: boolean
  /** An expert draft is being committed — locks Apply + Generate. */
  applying: boolean
  /** Generate disabled (no decision / no placement / resolving / applying). */
  generateDisabled: boolean
}>()

const emit = defineEmits<{
  (e: 'cancel'): void
  (e: 'open-expert'): void
  (e: 'apply'): void
  (e: 'generate'): void
}>()

const { t } = useI18n()

const applyDisabled = computed(() => !props.isDirty || !props.hasPlacement || props.applying)
</script>

<template>
  <footer class="modal-v2__footer">
    <button type="button" class="modal-v2__cancel" data-test="modal-v2-cancel" @click="emit('cancel')">
      {{ t('v2.modal.cancel') }}
    </button>
    <p
      v-if="applyError"
      class="modal-v2__apply-error"
      role="alert"
      data-test="modal-v2-apply-error"
    >
      {{ t('v2.modal.applyError', { message: applyError }) }}
    </p>
    <div class="modal-v2__footer-actions">
      <button
        v-if="isAssisted"
        type="button"
        class="modal-v2__expert-link"
        :title="t('v2.modal.openExpertHint')"
        data-test="modal-v2-open-expert"
        @click="emit('open-expert')"
      >
        {{ t('v2.modal.openExpert') }}
      </button>
      <!-- Expert "Appliquer" button: commits the V1 draft mutations
           (image preprocess, segmentation, master style, typography)
           back to the placement via /upload. Disabled when the draft
           is clean so a stray click can't trigger a pointless
           re-conversion. The dirty hint after the label tells the
           operator the button is meaningful right now. -->
      <button
        v-if="isExpert"
        type="button"
        class="modal-v2__apply-btn"
        :disabled="applyDisabled"
        :title="isDirty ? t('v2.modal.applyExpertHint') : t('v2.modal.applyExpertClean')"
        data-test="modal-v2-apply-expert"
        @click="emit('apply')"
      >
        {{ t('v2.modal.applyExpert') }}
        <span v-if="isDirty" aria-hidden="true" class="dirty-dot">●</span>
      </button>
      <button
        type="button"
        class="generate-btn"
        :disabled="generateDisabled"
        :title="!hasPlacement ? t('v2.modal.noPlacement') : undefined"
        data-test="confirm-button"
        @click="emit('generate')"
      >
        {{ t('v2.modal.generate') }}
      </button>
    </div>
  </footer>
</template>

<style scoped>
.modal-v2__footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
.modal-v2__apply-error {
  /* Sit inline between Cancel and the action buttons rather than push the
     footer taller. Self-contained error styling (the parent's shared
     ``.error`` class doesn't cross the scoped-style boundary). */
  margin: 0;
  flex: 1 1 auto;
  color: #fca5a5;
  background: rgba(69, 10, 10, 0.4);
  border: 1px solid #b91c1c;
  padding: 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
}
.modal-v2__footer-actions {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}
.modal-v2__cancel {
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 0.875rem;
  cursor: pointer;
  padding: 0.3rem 0.5rem;
  border-radius: 4px;
}
.modal-v2__cancel:hover {
  background: #1e293b;
  color: #e2e8f0;
}
.modal-v2__cancel:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.modal-v2__expert-link {
  border: none;
  background: transparent;
  color: #34d399;
  font-size: 0.875rem;
  cursor: pointer;
  padding: 0.3rem 0.4rem;
  border-radius: 4px;
}
.modal-v2__expert-link:hover {
  background: rgba(2, 44, 34, 0.4);
  text-decoration: underline;
}
.modal-v2__expert-link:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.modal-v2__apply-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.45rem 1rem;
  border: 1px solid #047857;
  background: rgba(2, 44, 34, 0.4);
  color: #a7f3d0;
  border-radius: 4px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition:
    background 0.12s ease,
    opacity 0.12s ease;
}
.modal-v2__apply-btn:hover:not(:disabled) {
  background: rgba(2, 44, 34, 0.7);
}
.modal-v2__apply-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.modal-v2__apply-btn:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.modal-v2__apply-btn .dirty-dot {
  font-size: 0.6875rem;
  color: #fbbf24;
}
.generate-btn {
  padding: 0.55rem 1.4rem;
  border: 1px solid #059669;
  background: #059669;
  color: white;
  border-radius: 4px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition:
    background 0.12s ease,
    transform 0.08s ease;
}
.generate-btn:hover:not(:disabled) {
  background: #10b981;
}
.generate-btn:active:not(:disabled) {
  transform: scale(0.97);
}
.generate-btn:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.generate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
