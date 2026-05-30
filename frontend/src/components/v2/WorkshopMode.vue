<script setup lang="ts">
// Workshop Mode (roadmap D.3 / audit #7 bonus).
//
// "Atelier" — full-screen, low-distraction surface for operators
// who are standing next to the machine during a live run. The
// existing rich workspace becomes overwhelming when the only
// question is "is it running, do I need to do anything?". Workshop
// Mode answers that with three large affordances: run state, the
// pending swap prompt (if any), one big Pause button.
//
// Toggle with Ctrl/Cmd + W (registered through useKeyboardShortcuts
// elsewhere) or by clicking the Atelier button in the header.

import type { PrintRun } from '../../api/client'

defineProps<{
  run: PrintRun | null
  /** When the run is paused for a swap, what the operator should do next. */
  nextActionHint?: string | null
}>()

const emit = defineEmits<{
  (e: 'exit'): void
  (e: 'pause'): void
  (e: 'resume'): void
}>()

function pct(run: PrintRun): number {
  if (run.total_lines <= 0) return 0
  return Math.round((run.acked_lines / run.total_lines) * 100)
}
</script>

<template>
  <div class="workshop-mode" data-test="workshop-mode" role="dialog" aria-modal="true">
    <header>
      <button
        type="button"
        class="exit"
        aria-label="Quitter le mode atelier"
        data-test="workshop-exit"
        @click="emit('exit')"
      >
        ×
      </button>
    </header>

    <main v-if="run" :data-test="`workshop-run-${run.id}`">
      <div class="state-line">
        <span class="dot" :class="run.state" />
        <span class="state-text">{{ run.state }}</span>
      </div>
      <div class="name">{{ run.name }}</div>
      <div class="progress">
        <div class="bar"><div class="fill" :style="{ width: `${pct(run)}%` }" /></div>
        <div class="percent">{{ pct(run) }} %</div>
      </div>
      <div v-if="nextActionHint && run.state === 'paused'" class="hint" data-test="workshop-hint">
        <strong>Action requise</strong>
        <p>{{ nextActionHint }}</p>
      </div>
      <div class="actions">
        <button
          v-if="run.state === 'running'"
          type="button"
          class="pause"
          data-test="workshop-pause"
          @click="emit('pause')"
        >
          Pause
        </button>
        <button
          v-else-if="run.state === 'paused'"
          type="button"
          class="resume"
          data-test="workshop-resume"
          @click="emit('resume')"
        >
          Reprendre
        </button>
      </div>
    </main>

    <main v-else class="empty" data-test="workshop-empty">
      <p>Aucun run actif.</p>
    </main>
  </div>
</template>

<style scoped>
.workshop-mode {
  position: fixed;
  inset: 0;
  background: #111;
  color: #f0f0f0;
  z-index: 10000;
  font-family: system-ui, sans-serif;
  display: flex;
  flex-direction: column;
}
header {
  display: flex;
  justify-content: flex-end;
  padding: 1rem;
}
.exit {
  background: transparent;
  border: 1px solid #555;
  color: #f0f0f0;
  font-size: 1.5rem;
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 50%;
  cursor: pointer;
}
main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1.5rem;
  padding: 0 2rem;
}
.state-line {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 1.5rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
.dot {
  width: 1rem;
  height: 1rem;
  border-radius: 50%;
  background: #888;
}
.dot.running {
  background: #4caf50;
  animation: pulse 1.5s infinite;
}
.dot.paused {
  background: #ffb300;
}
.dot.failed {
  background: #e53935;
}
.dot.completed {
  background: #1f6feb;
}
.dot.canceled {
  background: #888;
}
@keyframes pulse {
  0% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
  100% {
    opacity: 1;
  }
}
.name {
  font-size: 2rem;
  font-weight: 600;
  text-align: center;
}
.progress {
  width: 60%;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.bar {
  height: 1rem;
  background: #333;
  border-radius: 999px;
  overflow: hidden;
}
.fill {
  height: 100%;
  background: #1f6feb;
  transition: width 0.3s ease;
}
.percent {
  text-align: center;
  font-size: 1.25rem;
  font-family: ui-monospace, Menlo, monospace;
}
.hint {
  background: #fff4cc;
  color: #5b4a00;
  padding: 1rem 1.5rem;
  border-radius: 8px;
  max-width: 36rem;
  text-align: center;
}
.hint strong {
  display: block;
  font-size: 0.9rem;
  text-transform: uppercase;
  margin-bottom: 0.25rem;
}
.hint p {
  margin: 0;
  font-size: 1.1rem;
}
.actions {
  display: flex;
  gap: 1rem;
}
.actions button {
  padding: 1rem 3rem;
  font-size: 1.25rem;
  border-radius: 8px;
  border: none;
  cursor: pointer;
}
.pause {
  background: #ffb300;
  color: #111;
}
.resume {
  background: #1f6feb;
  color: white;
}
.empty {
  font-size: 1.25rem;
  color: #888;
}
</style>
