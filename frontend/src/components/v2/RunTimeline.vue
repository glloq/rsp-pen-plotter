<script setup lang="ts">
// Run timeline (roadmap C.6 / audit #7 §5).
//
// Renders the lifecycle of one PrintRun as a horizontal chain
// queued -> running -> paused/resumed -> done/fail. The current state
// is highlighted; everything before it is "done", everything after
// is "future". Pure / props-driven; the queue store wraps this
// component to display the active run on a dashboard.

import { computed } from 'vue'
import type { PrintRun, RunState } from '../../api/client'

const props = defineProps<{
  run: PrintRun
}>()

interface Phase {
  key: RunState
  label: string
}

// Canonical positive path. Failure / cancel render as separate
// status pills at the right instead of being inlined here so the
// timeline still reads left-to-right.
const PHASES: Phase[] = [
  { key: 'queued', label: 'En file' },
  { key: 'running', label: 'En cours' },
  { key: 'paused', label: 'Pause' },
  { key: 'completed', label: 'Terminé' },
]

const reachedIndex = computed<number>(() => {
  const state = props.run.state
  if (state === 'queued') return 0
  if (state === 'running') return 1
  if (state === 'paused') return 2
  if (state === 'completed') return 3
  return 1 // failed / canceled — at least we know it was queued + ran
})

const progressPercent = computed<number>(() => {
  if (props.run.total_lines <= 0) return 0
  return Math.round((props.run.acked_lines / props.run.total_lines) * 100)
})

const terminalBadge = computed<{ label: string; cls: string } | null>(() => {
  if (props.run.state === 'failed') return { label: 'Échec', cls: 'failed' }
  if (props.run.state === 'canceled') return { label: 'Annulé', cls: 'canceled' }
  return null
})
</script>

<template>
  <section class="run-timeline" :data-test="`run-timeline-${run.id}`">
    <header>
      <h4>{{ run.name }}</h4>
      <span class="profile">{{ run.profile_name }}</span>
      <span
        v-if="terminalBadge"
        :class="['badge', terminalBadge.cls]"
        :data-test="`run-badge-${terminalBadge.cls}`"
      >
        {{ terminalBadge.label }}
      </span>
    </header>

    <ol class="phases" aria-label="Run lifecycle">
      <li
        v-for="(phase, i) in PHASES"
        :key="phase.key"
        :class="{
          done: i < reachedIndex,
          active: i === reachedIndex && !terminalBadge,
          future: i > reachedIndex,
        }"
        :aria-current="i === reachedIndex ? 'step' : undefined"
        :data-test="`phase-${phase.key}`"
      >
        <span class="dot" />
        <span class="label">{{ phase.label }}</span>
      </li>
    </ol>

    <div class="progress" data-test="run-progress">
      <div class="bar">
        <div class="fill" :style="{ width: `${progressPercent}%` }" />
      </div>
      <span class="meta">
        {{ run.acked_lines }} / {{ run.total_lines }} lignes ({{ progressPercent }} %)
      </span>
    </div>

    <p v-if="run.error" class="error" data-test="run-error">
      {{ run.error }}
    </p>
  </section>
</template>

<style scoped>
.run-timeline {
  border: 1px solid #334155;
  background: #1e293b;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  font-size: 0.875rem;
  color: #f1f5f9;
}
header {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}
h4 {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
  flex: 1;
}
.profile {
  color: #94a3b8;
  font-size: 0.75rem;
  font-family: ui-monospace, Menlo, monospace;
}
.badge {
  font-size: 0.75rem;
  padding: 0.1rem 0.5rem;
  border-radius: 999px;
}
.badge.failed {
  background: rgba(69, 10, 10, 0.4);
  color: #fca5a5;
  border: 1px solid #b91c1c;
}
.badge.canceled {
  background: rgba(15, 23, 42, 0.6);
  color: #94a3b8;
  border: 1px solid #475569;
}
.phases {
  list-style: none;
  padding: 0;
  margin: 0 0 0.5rem 0;
  display: flex;
  gap: 0.5rem;
  position: relative;
}
.phases li {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  font-size: 0.75rem;
  color: #64748b;
}
.phases li.done {
  color: #059669;
}
.phases li.active {
  color: #34d399;
  font-weight: 600;
}
.phases li.future {
  opacity: 0.5;
}
.dot {
  display: inline-block;
  width: 0.65rem;
  height: 0.65rem;
  border-radius: 50%;
  background: currentColor;
  margin-bottom: 0.25rem;
}
.progress {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.bar {
  flex: 1;
  height: 0.5rem;
  background: #334155;
  border-radius: 999px;
  overflow: hidden;
}
.fill {
  height: 100%;
  background: #10b981;
  transition: width 0.2s ease;
}
.meta {
  font-size: 0.75rem;
  color: #94a3b8;
  font-family: ui-monospace, Menlo, monospace;
}
.error {
  margin-top: 0.5rem;
  padding: 0.5rem;
  background: rgba(69, 10, 10, 0.4);
  border: 1px solid #b91c1c;
  color: #fca5a5;
  border-radius: 4px;
  font-size: 0.75rem;
}
</style>
