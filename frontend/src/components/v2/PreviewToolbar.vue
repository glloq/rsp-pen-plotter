<script setup lang="ts">
// Floating controls for the editor preview pane: the Result / Original /
// Compare mode toggle (top-left) and the zoom in / out / reset cluster
// (top-right). Extracted from EditPreviewPane.vue (Phase 4 of the editor
// audit) as a pure presentational component — all state arrives via props,
// every action is emitted. The two clusters are absolutely positioned
// against the pane's ``.preview`` container (which crosses the component
// boundary fine), so this renders as a fragment with no wrapper.
//
// ``.stop`` on pointer/wheel/dblclick keeps a click on a control from also
// driving the pan / zoom / recentre gestures on the stage behind it.
import { useI18n } from 'vue-i18n'

defineProps<{
  viewMode: 'plot' | 'source' | 'split'
  /** Whether an original/source view is available at all. */
  canShowOriginal: boolean
  /** Whether the compare (split) mode is available. */
  canCompareOriginal: boolean
  /** Current zoom factor (1 = 100%). */
  zoom: number
}>()

const emit = defineEmits<{
  (e: 'set-mode', mode: 'plot' | 'source' | 'split'): void
  (e: 'zoom-in'): void
  (e: 'zoom-out'): void
  (e: 'reset-view'): void
}>()

const { t } = useI18n()
</script>

<template>
  <!-- Three-way mode toggle: Result / Original / Compare. -->
  <div
    v-if="canShowOriginal"
    class="mode-toggle"
    data-test="modal-v2-mode-toggle"
    @pointerdown.stop
    @wheel.stop
    @dblclick.stop
  >
    <button
      type="button"
      :class="{ active: viewMode === 'plot' }"
      :aria-pressed="viewMode === 'plot'"
      :title="t('v2.modal.viewPlot')"
      data-test="modal-v2-mode-plot"
      @click="emit('set-mode', 'plot')"
    >
      {{ t('v2.modal.viewPlot') }}
    </button>
    <button
      type="button"
      :class="{ active: viewMode === 'source' }"
      :aria-pressed="viewMode === 'source'"
      :title="t('v2.modal.viewOriginal')"
      data-test="modal-v2-mode-source"
      @click="emit('set-mode', 'source')"
    >
      {{ t('v2.modal.viewOriginal') }}
    </button>
    <button
      type="button"
      :class="{ active: viewMode === 'split' }"
      :aria-pressed="viewMode === 'split'"
      :disabled="!canCompareOriginal"
      :title="t('v2.modal.viewCompare')"
      data-test="modal-v2-mode-split"
      @click="emit('set-mode', 'split')"
    >
      {{ t('v2.modal.viewCompare') }}
    </button>
  </div>

  <div class="zoom" data-test="modal-v2-zoom" @pointerdown.stop @wheel.stop @dblclick.stop>
    <button
      type="button"
      :title="t('v2.modal.zoomIn')"
      :aria-label="t('v2.modal.zoomIn')"
      data-test="modal-v2-zoom-in"
      @click="emit('zoom-in')"
    >
      +
    </button>
    <button
      type="button"
      :title="t('v2.modal.zoomOut')"
      :aria-label="t('v2.modal.zoomOut')"
      data-test="modal-v2-zoom-out"
      @click="emit('zoom-out')"
    >
      −
    </button>
    <button
      type="button"
      class="zoom-reset"
      :title="t('v2.modal.resetView')"
      :aria-label="t('v2.modal.resetView')"
      data-test="modal-v2-zoom-reset"
      @click="emit('reset-view')"
    >
      {{ Math.round(zoom * 100) }}%
    </button>
  </div>
</template>

<style scoped>
.mode-toggle {
  position: absolute;
  top: 0.5rem;
  left: 0.5rem;
  display: inline-flex;
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid #334155;
  border-radius: 4px;
  overflow: hidden;
  z-index: 3;
}
.mode-toggle button {
  border: none;
  background: transparent;
  color: #cbd5e1;
  font-size: 0.75rem;
  padding: 0.25rem 0.55rem;
  cursor: pointer;
  font-weight: 500;
}
.mode-toggle button + button {
  border-left: 1px solid #334155;
}
.mode-toggle button.active {
  background: #059669;
  color: white;
}
.mode-toggle button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.mode-toggle button:hover:not(.active):not(:disabled) {
  background: #334155;
}
.mode-toggle button:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.zoom {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.zoom button {
  width: 1.9rem;
  height: 1.9rem;
  border: 1px solid #334155;
  background: rgba(15, 23, 42, 0.85);
  color: #e2e8f0;
  border-radius: 4px;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.zoom button:hover {
  background: #334155;
}
.zoom button:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.zoom-reset {
  font-size: 0.625rem !important;
  font-variant-numeric: tabular-nums;
}
</style>
