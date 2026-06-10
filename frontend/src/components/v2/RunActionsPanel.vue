<script setup lang="ts">
// Run actions panel (roadmap C.6 / audit #7 §5).
//
// Owns the operator-facing controls for an active run: Pause, Resume,
// Cancel + the next-action hint when the run is paused for a swap.
// Pause/Cancel ask for a confirm before emitting; Resume is one-click
// because the operator has already confirmed the swap on the head.
//
// The component is intentionally dumb about queue state — it emits
// events and the parent (queue store / page) calls into the API.

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PrintRun, RunState } from '../../api/client'

const props = defineProps<{
  run: PrintRun
  /** Operator-visible next action — set when paused for a swap. */
  nextActionHint?: string | null
}>()

const emit = defineEmits<{
  (e: 'pause'): void
  (e: 'resume'): void
  (e: 'cancel'): void
}>()

const { t } = useI18n()

const ACTIVE: RunState[] = ['queued', 'running', 'paused']

const isActive = computed<boolean>(() => ACTIVE.includes(props.run.state))
const canPause = computed<boolean>(() => props.run.state === 'running')
const canResume = computed<boolean>(() => props.run.state === 'paused')
const canCancel = computed<boolean>(() => isActive.value)

const confirming = ref<'pause' | 'cancel' | null>(null)

function startConfirm(action: 'pause' | 'cancel'): void {
  confirming.value = action
}

function dismissConfirm(): void {
  confirming.value = null
}

function commitConfirm(): void {
  if (confirming.value === 'pause') emit('pause')
  if (confirming.value === 'cancel') emit('cancel')
  confirming.value = null
}
</script>

<template>
  <section class="run-actions" :data-test="`run-actions-${run.id}`">
    <div v-if="run.state === 'paused' && nextActionHint" class="hint" data-test="next-action-hint">
      <strong>{{ t('v2.run.actionRequired') }}</strong> {{ nextActionHint }}
    </div>

    <div class="buttons">
      <button
        type="button"
        :disabled="!canPause"
        data-test="action-pause"
        @click="startConfirm('pause')"
      >
        {{ t('v2.run.pause') }}
      </button>
      <button
        type="button"
        :disabled="!canResume"
        class="primary"
        data-test="action-resume"
        @click="emit('resume')"
      >
        {{ t('v2.run.resume') }}
      </button>
      <button
        type="button"
        :disabled="!canCancel"
        class="danger"
        data-test="action-cancel"
        @click="startConfirm('cancel')"
      >
        {{ t('v2.run.cancel') }}
      </button>
    </div>

    <div v-if="confirming" class="confirm" role="alertdialog" data-test="confirm-dialog">
      <p>
        <strong>{{
          confirming === 'pause' ? t('v2.run.confirmPausePrompt') : t('v2.run.confirmCancelPrompt')
        }}</strong>
      </p>
      <div>
        <button type="button" data-test="confirm-cancel" @click="dismissConfirm">
          {{ t('v2.run.confirmNo') }}
        </button>
        <button type="button" class="primary" data-test="confirm-ok" @click="commitConfirm">
          {{ t('v2.run.confirmYes') }}
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.run-actions {
  font-size: 0.875rem;
  color: #f1f5f9;
}
.hint {
  background: rgba(69, 26, 3, 0.4);
  border: 1px solid #b45309;
  color: #fde68a;
  padding: 0.5rem 0.75rem;
  border-radius: 4px;
  margin-bottom: 0.5rem;
}
.buttons {
  display: flex;
  gap: 0.5rem;
}
button {
  padding: 0.4rem 0.75rem;
  border: 1px solid #334155;
  background: #1e293b;
  color: #e2e8f0;
  border-radius: 4px;
  cursor: pointer;
}
button:hover:not(:disabled) {
  background: #334155;
}
button:disabled {
  cursor: default;
  opacity: 0.45;
}
button.primary {
  background: #059669;
  color: white;
  border-color: #059669;
}
button.primary:hover:not(:disabled) {
  background: #10b981;
}
button.danger {
  border-color: #b91c1c;
  color: #fca5a5;
}
button.danger:hover:not(:disabled) {
  background: rgba(69, 10, 10, 0.5);
}
.confirm {
  margin-top: 0.5rem;
  padding: 0.75rem;
  border: 1px solid #475569;
  border-radius: 4px;
  background: #0f172a;
}
.confirm div {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
  justify-content: flex-end;
}
</style>
