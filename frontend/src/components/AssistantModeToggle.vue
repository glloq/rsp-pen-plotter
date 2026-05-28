<script setup lang="ts">
// Segmented toggle for the assisted/expert UX mode (roadmap C.1).
//
// This is the v0.2 single editor selector: Assisted maps to the
// six-step wizard (Modal V2), Expert maps to the rich per-layer
// editor (Modal V1). The mode is persisted in localStorage so the
// next session opens on the operator's preferred surface; keyboard
// shortcut Ctrl/Cmd + M flips it from anywhere.
import { useI18n } from 'vue-i18n'
import { useUiModeStore } from '../stores/uiMode'

const { t } = useI18n()
const ui = useUiModeStore()
</script>

<template>
  <div
    class="assistant-mode-toggle"
    role="group"
    :aria-label="t('v2.mode.groupLabel')"
  >
    <button
      type="button"
      :class="{ active: ui.isAssisted }"
      :aria-pressed="ui.isAssisted"
      :title="t('v2.mode.assistedHint')"
      data-test="assistant-mode-assisted"
      @click="ui.setMode('assisted')"
    >
      {{ t('v2.mode.assisted') }}
    </button>
    <button
      type="button"
      :class="{ active: ui.isExpert }"
      :aria-pressed="ui.isExpert"
      :title="t('v2.mode.expertHint')"
      data-test="assistant-mode-expert"
      @click="ui.setMode('expert')"
    >
      {{ t('v2.mode.expert') }}
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
.assistant-mode-toggle button {
  transition: background 0.12s ease, color 0.12s ease;
}
.assistant-mode-toggle button:hover:not(.active) {
  background: #f1f5f9;
}
</style>
