<script setup lang="ts">
// Loading overlay for the editor preview pane — spinner, label and the
// determinate progress bar shown while a /preview or /rerender is in
// flight. Extracted from EditPreviewPane.vue (Phase 4 of the editor audit)
// as a pure presentational component: the parent owns the percent (cost
// estimate blended with the SSE stream) and the stream label, this just
// renders them. Render it behind a ``v-if="loading"`` in the parent.
import { useI18n } from 'vue-i18n'

defineProps<{
  /** Blended progress 0..100 (cost-estimate EMA advanced by the SSE
   *  stream's real per-layer percent when one is active). */
  percent: number
  /** Whether the SSE progress stream is connected. */
  streamActive: boolean
  /** Current layer label from the stream, or null. */
  streamLabel: string | null
}>()

const { t } = useI18n()
</script>

<template>
  <div
    class="preview-overlay"
    role="status"
    aria-live="polite"
    data-test="modal-v2-preview-loading"
  >
    <span class="spinner" aria-hidden="true" />
    <span class="preview-overlay__label">
      {{ t('v2.modal.previewLoading') }}
      <span class="preview-overlay__percent" data-test="modal-v2-preview-percent">
        {{ percent }} %
      </span>
      <span v-if="streamActive && streamLabel" class="preview-overlay__layer">
        · {{ streamLabel }}
      </span>
    </span>
    <!-- Progress bar: estimated fill from the cost-estimator EMA (per
         algorithm × quality), advanced by the SSE stream's real per-layer
         percent when one is active. Always visible while computing. -->
    <div
      class="preview-overlay__bar"
      role="progressbar"
      :aria-valuenow="percent"
      aria-valuemin="0"
      aria-valuemax="100"
      data-test="modal-v2-preview-progress"
    >
      <div class="preview-overlay__bar-fill" :style="{ width: `${percent}%` }" />
    </div>
  </div>
</template>

<style scoped>
.preview-overlay {
  position: absolute;
  inset: auto 0 0 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  padding: 0.5rem 0.75rem;
  background: rgba(15, 23, 42, 0.88);
  font-size: 0.75rem;
  color: #cbd5e1;
}
.preview-overlay__label {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.preview-overlay__layer {
  color: #34d399;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.75rem;
}
.preview-overlay__percent {
  color: #94a3b8;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
}
.preview-overlay__bar {
  width: min(100%, 240px);
  height: 4px;
  background: #334155;
  border-radius: 999px;
  overflow: hidden;
}
.preview-overlay__bar-fill {
  height: 100%;
  background: #10b981;
  border-radius: 999px;
  transition: width 0.15s ease;
}
.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #334155;
  border-top-color: #10b981;
  border-radius: 50%;
  animation: preview-spin 0.7s linear infinite;
}
@keyframes preview-spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
  }
}
</style>
