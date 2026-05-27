<script setup lang="ts">
// Segmented toggle for the assisted/expert UX mode (roadmap C.1).
//
// Lightweight component meant to live in the modal header so the
// operator can flip mode per task without leaving the workflow.
import { useUiModeStore } from '../stores/uiMode'

const ui = useUiModeStore()
</script>

<template>
  <div class="assistant-mode-toggle" role="group" aria-label="UX mode">
    <button
      type="button"
      :class="{ active: ui.isAssisted }"
      :aria-pressed="ui.isAssisted"
      data-test="assistant-mode-assisted"
      @click="ui.setMode('assisted')"
    >
      Assisté
    </button>
    <button
      type="button"
      :class="{ active: ui.isExpert }"
      :aria-pressed="ui.isExpert"
      data-test="assistant-mode-expert"
      @click="ui.setMode('expert')"
    >
      Expert
    </button>
  </div>
</template>

<style scoped>
.assistant-mode-toggle {
  display: inline-flex;
  border: 1px solid #d0d0d0;
  border-radius: 4px;
  overflow: hidden;
  font-size: 0.85rem;
}
.assistant-mode-toggle button {
  padding: 0.25rem 0.75rem;
  border: none;
  background: white;
  color: #555;
  cursor: pointer;
}
.assistant-mode-toggle button.active {
  background: #1f6feb;
  color: white;
}
.assistant-mode-toggle button:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: -2px;
}
</style>
