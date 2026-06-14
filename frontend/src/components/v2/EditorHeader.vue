<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AssistantModeToggle from '../AssistantModeToggle.vue'
import { formatDuration, formatLengthMeters, type PreflightItem } from '../../composables/useEditorPreflight'

// Presentational header for the editor modal. The dialog keeps its
// accessible name via the parent's ``aria-label`` (no visible title, per
// operator feedback); this row carries the preflight + cost chips so the
// operator can read "am I ready, what will it cost?" at a glance, the
// assisted/expert toggle (expert only), and the close button. All state
// arrives via props; close is emitted.
defineProps<{
  hasPlacement: boolean
  preflightItems: PreflightItem[]
  hasEstimate: boolean
  estimatedDurationSeconds: number
  estimatedLengthMm: number
  requiredPenCount: number
  isExpert: boolean
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

const { t } = useI18n()
</script>

<template>
  <header class="modal-v2__header">
    <!-- No visible title (operator feedback) — the dialog keeps its
         accessible name via the aria-label on the parent dialog. -->

    <!-- Preflight + cost chips. ``data-test`` ids match the previous chips
         so existing Playwright selectors keep working. -->
    <ul
      v-if="hasPlacement"
      class="modal-v2__header-chips"
      :aria-label="t('v2.modal.preflightLabel')"
    >
      <li v-for="item in preflightItems" :key="item.id">
        <button
          v-if="!item.ok && item.onFix"
          type="button"
          class="modal-v2__hchip is-warn is-actionable"
          :data-test="`modal-v2-preflight-${item.id}`"
          :title="t('v2.modal.preflightFix')"
          @click="item.onFix"
        >
          <span aria-hidden="true">⚠</span>
          <span>{{ item.label }}</span>
        </button>
        <span
          v-else
          class="modal-v2__hchip"
          :class="item.ok ? 'is-ok' : 'is-warn'"
          :data-test="`modal-v2-preflight-${item.id}`"
        >
          <span aria-hidden="true">{{ item.ok ? '✓' : '⚠' }}</span>
          <span>{{ item.label }}</span>
        </span>
      </li>
      <li v-if="hasEstimate">
        <span
          class="modal-v2__hchip is-info"
          data-test="modal-v2-estimate-time"
          :title="t('v2.modal.estimateLabel')"
        >
          <span aria-hidden="true">⏱</span>
          <span>{{ formatDuration(estimatedDurationSeconds) }}</span>
        </span>
      </li>
      <li v-if="hasEstimate">
        <span class="modal-v2__hchip is-info" data-test="modal-v2-estimate-length">
          <span aria-hidden="true">📏</span>
          <span>{{ formatLengthMeters(estimatedLengthMm) }} m</span>
        </span>
      </li>
      <li v-if="requiredPenCount > 0">
        <span class="modal-v2__hchip is-info" data-test="modal-v2-estimate-pens">
          <span aria-hidden="true">🖊</span>
          <span>{{ requiredPenCount }}</span>
        </span>
      </li>
    </ul>

    <AssistantModeToggle v-if="isExpert" />
    <button
      type="button"
      class="close"
      :aria-label="t('settings.close')"
      data-test="modal-v2-close"
      @click="emit('close')"
    >
      ×
    </button>
  </header>
</template>

<style scoped>
.modal-v2__header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid #334155;
}
/* Preflight + estimate chip strip — reads "am I ready, what will it
   cost?" at a glance without the body reserving real estate. */
.modal-v2__header-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  list-style: none;
  padding: 0;
  margin: 0;
  flex: 1;
  min-width: 0;
}
.modal-v2__hchip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.18rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  border: 1px solid transparent;
  background: #1e293b;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.modal-v2__hchip.is-ok {
  border-color: #047857;
  color: #a7f3d0;
  background: rgba(2, 44, 34, 0.4);
}
.modal-v2__hchip.is-warn {
  border-color: #b45309;
  color: #fde68a;
  background: rgba(69, 26, 3, 0.4);
}
.modal-v2__hchip.is-info {
  border-color: #334155;
  color: #cbd5e1;
  background: #1e293b;
}
.modal-v2__hchip.is-actionable {
  cursor: pointer;
}
.modal-v2__hchip.is-actionable:hover {
  background: rgba(69, 26, 3, 0.7);
}
.modal-v2__hchip.is-actionable:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
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
</style>
