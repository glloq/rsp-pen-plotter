<script setup lang="ts">
// Beginner-editor "Personnaliser le style" panel.
//
// Extracted from EditModalV2 to keep that file under control as the
// modal accreted features. Manages its own collapsed/open state and
// per-style knob values internally; the parent only owns the
// ``modelValue`` array so it can build PolicyPasses for /rerender +
// Generate.
//
// Bitmap-only: vector and PDF pipelines bypass raster algorithms
// entirely, so we'd mislead the operator by surfacing chips that
// don't apply. The parent gates rendering via ``canCustomize``.

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  BEGINNER_STYLES,
  MAX_BEGINNER_STYLES,
  type BeginnerStyle,
  type CustomStyleSelection,
} from './beginnerStyles'
import type { AlgorithmId } from '../../data/printRegistry'

const props = defineProps<{
  modelValue: readonly CustomStyleSelection[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: CustomStyleSelection[]): void
}>()

const { t } = useI18n()

// Collapsed by default — the 80% case is "let the resolver pick" and
// the panel exists for operators who want to override.
const open = ref<boolean>(false)

function findStyle(id: AlgorithmId): BeginnerStyle | undefined {
  return BEGINNER_STYLES.find((s) => s.id === id)
}
function isSelected(id: AlgorithmId): boolean {
  return props.modelValue.some((s) => s.id === id)
}
function indexOf(id: AlgorithmId): number {
  return props.modelValue.findIndex((s) => s.id === id)
}
function toggleStyle(id: AlgorithmId): void {
  const idx = indexOf(id)
  if (idx >= 0) {
    emit(
      'update:modelValue',
      props.modelValue.filter((_, i) => i !== idx),
    )
    return
  }
  if (props.modelValue.length >= MAX_BEGINNER_STYLES) return
  const style = findStyle(id)
  if (!style) return
  emit('update:modelValue', [...props.modelValue, { id, knobValue: style.primaryKnob.default }])
}
function setKnob(idx: number, value: number): void {
  if (idx < 0 || idx >= props.modelValue.length) return
  const next = [...props.modelValue]
  next[idx] = { ...next[idx]!, knobValue: value }
  emit('update:modelValue', next)
}
function clearAll(): void {
  emit('update:modelValue', [])
}
</script>

<template>
  <div class="styles" data-test="modal-v2-styles">
    <button
      type="button"
      class="styles-toggle"
      :aria-expanded="open"
      data-test="modal-v2-styles-toggle"
      @click="open = !open"
    >
      <span aria-hidden="true" class="styles-caret">{{ open ? '▾' : '▸' }}</span>
      <span>{{ t('v2.modal.styleCustom') }}</span>
      <span v-if="modelValue.length > 0" class="styles-count" data-test="modal-v2-styles-count">{{
        modelValue.length
      }}</span>
    </button>

    <div v-if="open" class="styles-body">
      <p class="styles-hint">
        {{ t('v2.modal.styleHint', { max: MAX_BEGINNER_STYLES }) }}
      </p>

      <ul class="style-grid" :aria-label="t('v2.modal.styleCustom')">
        <li v-for="style in BEGINNER_STYLES" :key="style.id">
          <button
            type="button"
            class="style-chip"
            :class="{ 'is-selected': isSelected(style.id) }"
            :disabled="!isSelected(style.id) && modelValue.length >= MAX_BEGINNER_STYLES"
            :title="
              !isSelected(style.id) && modelValue.length >= MAX_BEGINNER_STYLES
                ? t('v2.modal.styleMax', { max: MAX_BEGINNER_STYLES })
                : `${t(style.labelKey)} — ${t(style.descriptionKey)}`
            "
            :aria-pressed="isSelected(style.id)"
            :aria-label="`${t(style.labelKey)}. ${t(style.descriptionKey)}`"
            :data-test="`modal-v2-style-${style.id}`"
            @click="toggleStyle(style.id)"
          >
            <!-- eslint-disable-next-line vue/no-v-html -->
            <svg
              class="style-thumb"
              viewBox="0 0 24 24"
              aria-hidden="true"
              v-html="style.thumbnailSvg"
            />
            <span class="style-name">{{ t(style.labelKey) }}</span>
            <span v-if="isSelected(style.id)" class="style-step" aria-hidden="true">{{
              indexOf(style.id) + 1
            }}</span>
          </button>
        </li>
      </ul>

      <ol v-if="modelValue.length" class="style-stack" :aria-label="t('v2.modal.styleStackLabel')">
        <li
          v-for="(sel, idx) in modelValue"
          :key="`stack-${sel.id}`"
          class="style-row"
          :data-test="`modal-v2-style-row-${sel.id}`"
        >
          <span class="style-row-step" aria-hidden="true">{{ idx + 1 }}</span>
          <span class="style-row-name">
            <!-- eslint-disable-next-line vue/no-v-html -->
            <svg
              class="style-row-thumb"
              viewBox="0 0 24 24"
              aria-hidden="true"
              v-html="findStyle(sel.id)!.thumbnailSvg"
            />
            <span class="style-row-text">
              <span class="style-row-title">{{ t(findStyle(sel.id)!.labelKey) }}</span>
              <span class="style-row-desc">{{ t(findStyle(sel.id)!.descriptionKey) }}</span>
            </span>
          </span>
          <label class="style-knob">
            <span class="style-knob-label">{{ t(findStyle(sel.id)!.primaryKnob.labelKey) }}</span>
            <input
              type="range"
              :min="findStyle(sel.id)!.primaryKnob.min"
              :max="findStyle(sel.id)!.primaryKnob.max"
              :step="findStyle(sel.id)!.primaryKnob.step"
              :value="sel.knobValue"
              :aria-label="t(findStyle(sel.id)!.primaryKnob.labelKey)"
              :data-test="`modal-v2-style-knob-${sel.id}`"
              @input="setKnob(idx, +($event.target as HTMLInputElement).value)"
            />
            <span class="style-knob-value">
              {{ sel.knobValue }}
              <span v-if="findStyle(sel.id)!.primaryKnob.unit">
                {{ findStyle(sel.id)!.primaryKnob.unit }}
              </span>
            </span>
          </label>
          <button
            type="button"
            class="style-remove"
            :title="t('v2.modal.styleRemove')"
            :aria-label="t('v2.modal.styleRemove')"
            :data-test="`modal-v2-style-remove-${sel.id}`"
            @click="toggleStyle(sel.id)"
          >
            ×
          </button>
        </li>
      </ol>

      <button
        v-if="modelValue.length"
        type="button"
        class="style-clear"
        data-test="modal-v2-style-clear"
        @click="clearAll"
      >
        {{ t('v2.modal.styleClear') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.styles {
  margin: 0.75rem 0 0;
}
.styles-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border: 1px solid #334155;
  background: #1e293b;
  color: #e2e8f0;
  padding: 0.3rem 0.7rem;
  border-radius: 4px;
  font-size: 0.875rem;
  cursor: pointer;
}
.styles-toggle:hover {
  background: #334155;
}
.styles-toggle:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.styles-caret {
  font-size: 0.6875rem;
  width: 0.6rem;
  display: inline-block;
  text-align: center;
}
.styles-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.2rem;
  height: 1.2rem;
  padding: 0 0.35rem;
  border-radius: 999px;
  background: #059669;
  color: white;
  font-size: 0.6875rem;
  font-weight: 600;
}
.styles-body {
  margin-top: 0.5rem;
  padding: 0.65rem 0.75rem;
  border: 1px solid #334155;
  border-radius: 8px;
  background: #1e293b;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.styles-hint {
  margin: 0;
  font-size: 0.75rem;
  color: #94a3b8;
}

.style-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.35rem;
  list-style: none;
  padding: 0;
  margin: 0;
}
.style-chip {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.15rem;
  padding: 0.4rem 0.3rem;
  border: 1px solid #334155;
  background: #0f172a;
  border-radius: 4px;
  font-size: 0.75rem;
  color: #cbd5e1;
  cursor: pointer;
  transition:
    background 0.12s ease,
    border-color 0.12s ease;
  width: 100%;
}
.style-chip:hover:not(:disabled):not(.is-selected) {
  background: #1e293b;
  border-color: #475569;
}
.style-chip.is-selected {
  border-color: #059669;
  background: rgba(2, 44, 34, 0.45);
  box-shadow: inset 0 0 0 1px #059669;
  color: #6ee7b7;
  font-weight: 600;
}
.style-chip:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.style-chip:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.style-thumb {
  width: 28px;
  height: 28px;
  display: block;
}
.style-name {
  font-size: 0.6875rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.style-step {
  position: absolute;
  top: 2px;
  right: 4px;
  width: 1rem;
  height: 1rem;
  border-radius: 999px;
  background: #059669;
  color: white;
  font-size: 0.625rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.style-stack {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.style-row {
  display: grid;
  grid-template-columns: auto auto 1fr auto;
  gap: 0.5rem;
  align-items: center;
  padding: 0.35rem 0.5rem;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 4px;
  font-size: 0.75rem;
}
.style-row-step {
  width: 1.2rem;
  height: 1.2rem;
  border-radius: 999px;
  background: #059669;
  color: white;
  font-size: 0.6875rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.style-row-name {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  min-width: 0;
  color: #e2e8f0;
}
.style-row-thumb {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  color: #34d399;
}
.style-row-text {
  display: inline-flex;
  flex-direction: column;
  gap: 0.05rem;
  min-width: 0;
}
.style-row-title {
  font-weight: 600;
  font-size: 0.75rem;
  white-space: nowrap;
}
.style-row-desc {
  font-size: 0.6875rem;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.style-knob {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.6875rem;
  color: #94a3b8;
  min-width: 0;
}
.style-knob-label {
  white-space: nowrap;
}
.style-knob input[type='range'] {
  flex: 1;
  min-width: 4rem;
  accent-color: #10b981;
}
.style-knob-value {
  min-width: 3.2rem;
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: #cbd5e1;
}
.style-remove {
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 1rem;
  line-height: 1;
  cursor: pointer;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
}
.style-remove:hover {
  background: rgba(69, 10, 10, 0.5);
  color: #fca5a5;
}
.style-remove:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.style-clear {
  align-self: flex-start;
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 0.75rem;
  cursor: pointer;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
}
.style-clear:hover {
  background: #334155;
  color: #e2e8f0;
  text-decoration: underline;
}
</style>
