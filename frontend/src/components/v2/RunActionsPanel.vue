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
      <strong>Action requise&nbsp;:</strong> {{ nextActionHint }}
    </div>

    <div class="buttons">
      <button
        type="button"
        :disabled="!canPause"
        data-test="action-pause"
        @click="startConfirm('pause')"
      >
        Pause
      </button>
      <button
        type="button"
        :disabled="!canResume"
        class="primary"
        data-test="action-resume"
        @click="emit('resume')"
      >
        Reprendre
      </button>
      <button
        type="button"
        :disabled="!canCancel"
        class="danger"
        data-test="action-cancel"
        @click="startConfirm('cancel')"
      >
        Annuler
      </button>
    </div>

    <div
      v-if="confirming"
      class="confirm"
      role="alertdialog"
      data-test="confirm-dialog"
    >
      <p>
        Confirmer&nbsp;:
        <strong>{{ confirming === 'pause' ? 'Mettre en pause' : 'Annuler le run' }}</strong>&nbsp;?
      </p>
      <div>
        <button type="button" data-test="confirm-cancel" @click="dismissConfirm">
          Non
        </button>
        <button type="button" class="primary" data-test="confirm-ok" @click="commitConfirm">
          Oui
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.run-actions {
  font-family: system-ui, sans-serif;
  font-size: 0.875rem;
}
.hint {
  background: #fff4cc;
  border: 1px solid #d9b800;
  color: #5b4a00;
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
  border: 1px solid #d0d0d0;
  background: white;
  border-radius: 4px;
  cursor: pointer;
}
button:disabled {
  cursor: default;
  opacity: 0.45;
}
button.primary {
  background: #1f6feb;
  color: white;
  border-color: #1f6feb;
}
button.danger {
  border-color: #b71c1c;
  color: #b71c1c;
}
.confirm {
  margin-top: 0.5rem;
  padding: 0.75rem;
  border: 1px solid #888;
  border-radius: 4px;
  background: #fafafa;
}
.confirm div {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
  justify-content: flex-end;
}
</style>
