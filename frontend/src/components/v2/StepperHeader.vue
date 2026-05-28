<script setup lang="ts">
// Stepper header for the v0.2 Modal V2 (roadmap C.2). Renders one
// chip per step + a current-step indicator. Steps before the active
// one are clickable; future steps are disabled by default since the
// modal walks forward (the operator can still jump back via Previous).
//
// Keyboard: Arrow Left/Right move the active chip's focus across
// past steps, Home/End jump to the first/last visited. Enter activates
// the focused chip — Vue's default ``button`` keyboard handling.

import { ref } from 'vue'

const props = defineProps<{
  steps: { id: string; label: string }[]
  activeIndex: number
}>()

const emit = defineEmits<{ (e: 'jump', index: number): void }>()

const buttons = ref<HTMLButtonElement[]>([])

function setButtonRef(el: Element | null, i: number): void {
  if (el instanceof HTMLButtonElement) {
    buttons.value[i] = el
  }
}

function onKey(event: KeyboardEvent, i: number): void {
  // ``activeIndex`` is the rightmost reachable step (everything past
  // it is disabled). Keyboard navigation respects that bound.
  const max = props.activeIndex
  let target: number | null = null
  if (event.key === 'ArrowLeft' && i > 0) target = i - 1
  if (event.key === 'ArrowRight' && i < max) target = i + 1
  if (event.key === 'Home') target = 0
  if (event.key === 'End') target = max
  if (target === null) return
  event.preventDefault()
  buttons.value[target]?.focus()
}
</script>

<template>
  <ol class="stepper-header" :aria-label="'Steps'">
    <li
      v-for="(step, i) in steps"
      :key="step.id"
      class="step"
      :class="{
        active: i === activeIndex,
        done: i < activeIndex,
      }"
      :aria-current="i === activeIndex ? 'step' : undefined"
    >
      <button
        :ref="(el) => setButtonRef(el as Element | null, i)"
        type="button"
        :disabled="i > activeIndex"
        :data-test="`stepper-step-${step.id}`"
        :aria-label="`${i + 1} — ${step.label}`"
        @click="emit('jump', i)"
        @keydown="onKey($event, i)"
      >
        <span class="num">{{ i + 1 }}</span>
        <span class="label">{{ step.label }}</span>
      </button>
    </li>
  </ol>
</template>

<style scoped>
.stepper-header {
  display: flex;
  gap: 0.5rem;
  padding: 0;
  margin: 0 0 1rem 0;
  list-style: none;
}
.step button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.75rem;
  border: 1px solid #d0d0d0;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
  color: #555;
  transition: background 0.12s ease, border-color 0.12s ease, transform 0.08s ease;
}
.step button:disabled {
  cursor: default;
  opacity: 0.5;
}
.step button:not(:disabled):hover {
  background: #f1f5f9;
  border-color: #94a3b8;
}
.step button:not(:disabled):active {
  transform: scale(0.97);
}
.step button:focus-visible {
  outline: 2px solid #1f6feb;
  outline-offset: 2px;
}
.step.active button {
  background: #1f6feb;
  color: white;
  border-color: #1f6feb;
}
.step.done button {
  background: #e6f4ea;
  border-color: #4caf50;
  color: #1b5e20;
}
.num {
  display: inline-flex;
  width: 1.25rem;
  height: 1.25rem;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.1);
  font-size: 0.75rem;
  font-weight: 600;
}
.step.active .num {
  background: rgba(255, 255, 255, 0.25);
}
</style>
