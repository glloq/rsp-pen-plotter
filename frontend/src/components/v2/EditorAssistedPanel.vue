<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { Goal, PaletteMode } from '../../domain/policy/schemas'
import StyleCustomizer from './StyleCustomizer.vue'
import type { CustomStyleSelection } from './beginnerStyles'

// Assisted surface for the editor modal: the guided single screen —
// intent picker (fast / balanced / quality), palette-source toggle
// (machine magazine vs. free inventory) and the optional beginner
// style stack. Three clicks max to a usable Generate. Pure presentation:
// the current goal / palette / style stack arrive via props, and the
// changes are emitted (goal/palette) or v-modelled (custom styles).
const INTENTS: readonly Goal[] = ['fast', 'balanced', 'quality'] as const

defineProps<{
  goal: Goal
  paletteMode: PaletteMode
  /** Bitmap-only — vector / PDF pipelines bypass raster algorithms. */
  canCustomizeStyles: boolean
  customStyles: CustomStyleSelection[]
}>()

const emit = defineEmits<{
  (e: 'select-goal', goal: Goal): void
  (e: 'select-palette', mode: PaletteMode): void
  (e: 'update:customStyles', styles: CustomStyleSelection[]): void
}>()

const { t } = useI18n()
</script>

<template>
  <div>
    <!-- Primary control: what matters most. Single-screen, three clicks
         max to a usable Generate. -->
    <fieldset class="modal-v2__intent">
      <legend>{{ t('v2.modal.chooseIntent') }}</legend>
      <div class="intent-grid">
        <button
          v-for="opt in INTENTS"
          :key="opt"
          type="button"
          :class="{ active: goal === opt }"
          :aria-pressed="goal === opt"
          :data-test="`intent-${opt}`"
          @click="emit('select-goal', opt)"
        >
          <strong>{{ t(`v2.intent.${opt}`) }}</strong>
          <span class="intent-desc">{{ t(`v2.intent.${opt}Desc`) }}</span>
        </button>
      </div>
    </fieldset>

    <!-- Secondary control: where the colours come from. Machine magazine
         is the safe default (only pens actually loaded); "free" lets the
         resolver pick from the full palette for operators who'll swap
         pens by hand. -->
    <fieldset class="modal-v2__palette">
      <legend>{{ t('v2.modal.paletteLabel') }}</legend>
      <div class="palette-toggle">
        <button
          type="button"
          :class="{ active: paletteMode === 'machine_only' }"
          :aria-pressed="paletteMode === 'machine_only'"
          data-test="palette-machine_only"
          @click="emit('select-palette', 'machine_only')"
        >
          {{ t('v2.modal.paletteMachine') }}
        </button>
        <button
          type="button"
          :class="{ active: paletteMode === 'free' }"
          :aria-pressed="paletteMode === 'free'"
          data-test="palette-free"
          @click="emit('select-palette', 'free')"
        >
          {{ t('v2.modal.paletteFree') }}
        </button>
      </div>
    </fieldset>

    <!-- Optional "stack your own styles" panel. Empty stack = the
         resolver wins (default experience); non-empty stack overrides the
         algorithm at preview + Generate time. The subcomponent owns the
         picker UI; this panel forwards the selection as v-model. -->
    <StyleCustomizer
      v-if="canCustomizeStyles"
      :model-value="customStyles"
      @update:model-value="(v: CustomStyleSelection[]) => emit('update:customStyles', v)"
    />
  </div>
</template>

<style scoped>
.modal-v2__intent {
  border: none;
  padding: 0;
  margin: 0 0 0.5rem;
}
.modal-v2__intent legend {
  padding: 0;
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: #e2e8f0;
}
.intent-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.5rem;
}
.intent-grid button {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.2rem;
  padding: 0.65rem 0.75rem;
  border: 1px solid #334155;
  border-radius: 8px;
  background: #1e293b;
  color: inherit;
  transition:
    background 0.12s ease,
    border-color 0.12s ease,
    transform 0.08s ease;
  cursor: pointer;
  text-align: left;
}
.intent-grid button.active {
  border-color: #059669;
  background: rgba(2, 44, 34, 0.45);
  box-shadow: inset 0 0 0 1px #059669;
}
.intent-grid button:hover:not(.active) {
  background: #334155;
  border-color: #475569;
}
.intent-grid button:active {
  transform: scale(0.98);
}
.intent-grid button:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.intent-desc {
  font-size: 0.75rem;
  color: #94a3b8;
  font-weight: 400;
}
.modal-v2__palette {
  border: none;
  padding: 0;
  margin: 0.75rem 0 0;
}
.modal-v2__palette legend {
  padding: 0;
  margin-bottom: 0.4rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: #e2e8f0;
}
.palette-toggle {
  display: inline-flex;
  border: 1px solid #334155;
  border-radius: 4px;
  overflow: hidden;
}
.palette-toggle button {
  padding: 0.35rem 0.8rem;
  border: none;
  background: #1e293b;
  color: #cbd5e1;
  font-size: 0.75rem;
  cursor: pointer;
  transition: background 0.12s ease;
}
.palette-toggle button + button {
  border-left: 1px solid #334155;
}
.palette-toggle button.active {
  background: rgba(2, 44, 34, 0.6);
  color: #6ee7b7;
  font-weight: 600;
}
.palette-toggle button:hover:not(.active) {
  background: #334155;
}
.palette-toggle button:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
</style>
