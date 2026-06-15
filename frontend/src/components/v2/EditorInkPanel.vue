<script setup lang="ts">
// Per-layer ink swatches, in draw order, under the preview. Each chip is a
// one-click visibility toggle (👁 / ⊘ + strike-through) so a beginner can
// mute a layer without leaving the modal, plus a 🎨 button that opens a
// colour-assignment popover (the full magazine ∪ inventory picker) so the
// operator can swap the ink a layer draws with right from the preview. When
// the resolver fell back because nothing in the magazine matched, a secondary
// "Charger" CTA on the chip jumps straight to the magazine editor.
//
// Extracted from ``EditModalV2.vue`` (audit P2 — "panneau des encres" +
// "visibilité des calques") as a presentational component. It holds only the
// "which popover is open" UI state: visibility + assignment are read through
// the props and all store writes are emitted back to the host.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ColorAssignment } from '../../api/client'
import type { InkSwatch } from '../../composables/useEditorInkSwatches'
import AssignedColorPicker from '../edit/AssignedColorPicker.vue'

const props = defineProps<{
  /** Layers to render, in draw order. Empty hides the whole panel. */
  swatches: InkSwatch[]
  /** Current visibility of a layer id — kept as a getter so the host's
   *  reactive store read is tracked by this component's render. */
  isVisible: (layerId: string) => boolean
  /** Source-driven pool the "↻ auto" nearest-match reads from. */
  effectivePalette: readonly string[]
  /** Full magazine ∪ inventory set offered for a manual pick. */
  pickerPalette: readonly string[]
}>()

const emit = defineEmits<{
  (e: 'toggle', layerId: string): void
  (e: 'load-ink'): void
  (e: 'pick', payload: { layerId: string; hex: string; assignment: ColorAssignment }): void
  (e: 'reset', payload: { layerId: string; hex: string | null }): void
}>()

const { t } = useI18n()

// Which chip's assignment popover is open (layerId), or null when none.
const openLayerId = ref<string | null>(null)
function toggleAssign(layerId: string): void {
  openLayerId.value = openLayerId.value === layerId ? null : layerId
}
function onPick(layerId: string, payload: { hex: string; assignment: ColorAssignment }): void {
  emit('pick', { layerId, ...payload })
  openLayerId.value = null
}
function onReset(layerId: string, payload: { hex: string | null }): void {
  emit('reset', { layerId, ...payload })
  openLayerId.value = null
}
</script>

<template>
  <div
    v-if="props.swatches.length"
    class="modal-v2__inks"
    data-test="modal-v2-inks"
    :aria-label="t('v2.modal.inksLabel')"
  >
    <span class="modal-v2__inks-label">{{ t('v2.modal.inksLabel') }}</span>
    <ul class="modal-v2__inks-list">
      <li v-for="ink in props.swatches" :key="ink.layerId" class="modal-v2__ink-item">
        <button
          type="button"
          class="modal-v2__ink"
          :class="{
            'is-fallback': ink.isFallback,
            'is-hidden': !props.isVisible(ink.layerId),
          }"
          :aria-pressed="props.isVisible(ink.layerId)"
          :title="props.isVisible(ink.layerId) ? t('v2.modal.layerHide') : t('v2.modal.layerShow')"
          :data-test="`modal-v2-ink-${ink.layerId}`"
          @click="emit('toggle', ink.layerId)"
        >
          <span class="modal-v2__ink-eye" aria-hidden="true">{{
            props.isVisible(ink.layerId) ? '👁' : '⊘'
          }}</span>
          <span
            class="modal-v2__ink-swatch"
            :style="{ backgroundColor: ink.hex }"
            aria-hidden="true"
          />
          <span class="modal-v2__ink-name">{{ ink.displayName }}</span>
        </button>
        <!-- Assign another colour to this layer. Disabled for the rare
             live-preview cluster with no committed layer yet. -->
        <button
          v-if="ink.layer"
          type="button"
          class="modal-v2__ink-assign"
          :class="{ 'is-open': openLayerId === ink.layerId }"
          :aria-expanded="openLayerId === ink.layerId"
          :title="
            openLayerId === ink.layerId
              ? t('v2.modal.layerAssignClose')
              : t('v2.modal.layerAssign')
          "
          :aria-label="t('v2.modal.layerAssign')"
          :data-test="`modal-v2-ink-assign-${ink.layerId}`"
          @click="toggleAssign(ink.layerId)"
        >
          🎨
        </button>
        <button
          v-if="ink.isFallback"
          type="button"
          class="modal-v2__ink-cta"
          :title="t('v2.modal.inkFallback', { hex: ink.hex })"
          :aria-label="t('v2.modal.inkFallbackCta')"
          :data-test="`modal-v2-ink-load-${ink.layerId}`"
          @click="emit('load-ink')"
        >
          {{ t('v2.modal.inkFallbackCta') }}
        </button>

        <!-- Per-layer colour picker popover (full magazine ∪ inventory). -->
        <div
          v-if="ink.layer && openLayerId === ink.layerId"
          class="modal-v2__ink-popover"
          :data-test="`modal-v2-ink-popover-${ink.layerId}`"
        >
          <AssignedColorPicker
            :layer="ink.layer"
            :effective-palette="props.effectivePalette"
            :picker-palette="props.pickerPalette"
            @pick="(p) => onPick(ink.layerId, p)"
            @reset="(p) => onReset(ink.layerId, p)"
          />
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.modal-v2__inks {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin: 0;
}
.modal-v2__inks-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.modal-v2__inks-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  list-style: none;
  padding: 0;
  margin: 0;
}
.modal-v2__ink-item {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
}
.modal-v2__ink {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.15rem 0.55rem 0.15rem 0.35rem;
  border: 1px solid #334155;
  border-radius: 999px;
  background: #1e293b;
  font-size: 0.75rem;
  color: #cbd5e1;
  max-width: 14rem;
  cursor: pointer;
  transition:
    background 0.12s ease,
    opacity 0.15s ease;
}
.modal-v2__ink:hover {
  background: #334155;
}
.modal-v2__ink:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.modal-v2__ink.is-hidden {
  opacity: 0.5;
}
.modal-v2__ink.is-hidden .modal-v2__ink-name {
  text-decoration: line-through;
}
.modal-v2__ink.is-fallback {
  border-color: #b45309;
  background: rgba(69, 26, 3, 0.4);
  color: #fde68a;
}
.modal-v2__ink-eye {
  font-size: 0.6875rem;
  line-height: 1;
  opacity: 0.7;
}
.modal-v2__ink-swatch {
  display: inline-block;
  width: 0.85rem;
  height: 0.85rem;
  border-radius: 50%;
  border: 1px solid rgba(241, 245, 249, 0.3);
  flex-shrink: 0;
}
.modal-v2__ink-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.modal-v2__ink-cta {
  border: 1px solid #b45309;
  background: rgba(69, 26, 3, 0.4);
  color: #fde68a;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.6875rem;
  cursor: pointer;
  white-space: nowrap;
}
.modal-v2__ink-cta:hover {
  background: rgba(69, 26, 3, 0.7);
}
.modal-v2__ink-cta:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
.modal-v2__ink-assign {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.4rem;
  height: 1.4rem;
  border: 1px solid #334155;
  border-radius: 999px;
  background: #1e293b;
  font-size: 0.7rem;
  line-height: 1;
  cursor: pointer;
  transition:
    background 0.12s ease,
    border-color 0.12s ease;
}
.modal-v2__ink-assign:hover {
  background: #334155;
}
.modal-v2__ink-assign.is-open {
  border-color: #10b981;
  background: rgba(6, 78, 59, 0.4);
}
.modal-v2__ink-assign:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
/* Popover floats above the chip strip so a long inventory doesn't push the
   preview around. The chip item is the positioning context. */
.modal-v2__ink-popover {
  position: absolute;
  top: calc(100% + 0.3rem);
  left: 0;
  z-index: 20;
  width: 16rem;
  max-width: 80vw;
  border: 1px solid #334155;
  border-radius: 0.5rem;
  background: #0f172a;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
}
</style>
