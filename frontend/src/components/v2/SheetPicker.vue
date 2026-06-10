<script setup lang="ts">
// Sheet-format picker for the editor modal.
//
// Lets the operator change the paper format (A6 / A5 / A4 / A3 / A2 /
// Letter) and orientation (portrait / landscape) from *inside* the
// modal — previously the only way to pick a sheet was the LayoutSection
// outside the editor, which forced a context switch every time the
// operator wanted to verify the artwork's footprint at a different
// scale. Writes through ``ui.setPreviewSheet`` so the change is global
// (the plan view and the preview pane both reflect it).
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../../stores/job'
import { useUiStore } from '../../stores/ui'
import type { PreviewSheet } from '../../stores/ui'

const { t } = useI18n()
const ui = useUiStore()
const job = useJobStore()

// Commit a sheet change AND refit the active artwork to the new page.
// The preview pane sizes the artwork as ``artwork_mm / sheet_mm``, so
// without the refit picking a bigger format left the drawing at its old
// physical size — it only *looked* right on formats smaller than the
// artwork, where the preview's 100 % clamp made it fill the sheet.
function commitSheet(sheet: PreviewSheet): void {
  ui.setPreviewSheet(sheet)
  job.fitSelectedPlacementToSheet(sheet)
}

interface SheetPreset {
  name: string
  w: number
  h: number
}

// Same preset list as LayoutSection.vue — kept identical so a sheet
// the operator picks here matches the one the plan view advertises.
const PRESETS: SheetPreset[] = [
  { name: 'A6', w: 105, h: 148 },
  { name: 'A5', w: 148, h: 210 },
  { name: 'A4', w: 210, h: 297 },
  { name: 'A3', w: 297, h: 420 },
  { name: 'A2', w: 420, h: 594 },
  { name: 'Letter', w: 216, h: 279 },
]

type Orientation = 'portrait' | 'landscape'

const currentOrientation = computed<Orientation>(() => {
  const s = ui.previewSheet
  if (!s) return 'portrait'
  return s.width_mm > s.height_mm ? 'landscape' : 'portrait'
})

// "Active" detection: a preset matches the live sheet when (after
// orientation normalisation) the dimensions agree to the millimetre.
// Floats coming back from the backend can carry tiny rounding errors
// so we tolerate ±0.5 mm.
function isActive(p: SheetPreset): boolean {
  const s = ui.previewSheet
  if (!s) return false
  const presetW = currentOrientation.value === 'landscape' ? p.h : p.w
  const presetH = currentOrientation.value === 'landscape' ? p.w : p.h
  return Math.abs(s.width_mm - presetW) < 0.5 && Math.abs(s.height_mm - presetH) < 0.5
}

function applyPreset(p: SheetPreset): void {
  const landscape = currentOrientation.value === 'landscape'
  commitSheet({
    width_mm: landscape ? p.h : p.w,
    height_mm: landscape ? p.w : p.h,
    x_mm: ui.previewSheet?.x_mm ?? 0,
    y_mm: ui.previewSheet?.y_mm ?? 0,
  })
}

function setOrientation(o: Orientation): void {
  // Re-shape the current sheet by swapping width/height so the
  // operator's pick keeps its format but flips its long axis. When
  // there's no live sheet yet we seed an A4 in the chosen orientation
  // so the orientation toggle is never a no-op.
  if (!ui.previewSheet) {
    const a4 = PRESETS.find((p) => p.name === 'A4')!
    commitSheet({
      width_mm: o === 'landscape' ? a4.h : a4.w,
      height_mm: o === 'landscape' ? a4.w : a4.h,
      x_mm: 0,
      y_mm: 0,
    })
    return
  }
  const w = ui.previewSheet.width_mm
  const h = ui.previewSheet.height_mm
  const big = Math.max(w, h)
  const small = Math.min(w, h)
  commitSheet({
    width_mm: o === 'landscape' ? big : small,
    height_mm: o === 'landscape' ? small : big,
    x_mm: ui.previewSheet.x_mm,
    y_mm: ui.previewSheet.y_mm,
  })
}
</script>

<template>
  <div class="sheet-picker" data-test="modal-v2-sheet-picker">
    <span class="sheet-picker__label">{{ t('v2.modal.sheetPickerLabel') }}</span>
    <div class="sheet-picker__row">
      <button
        v-for="p in PRESETS"
        :key="p.name"
        type="button"
        class="sheet-picker__chip"
        :class="{ active: isActive(p) }"
        :aria-pressed="isActive(p)"
        :title="`${p.w}×${p.h} mm`"
        :data-test="`sheet-preset-${p.name}`"
        @click="applyPreset(p)"
      >
        {{ p.name }}
      </button>
      <span class="sheet-picker__sep" aria-hidden="true">|</span>
      <button
        type="button"
        class="sheet-picker__chip"
        :class="{ active: currentOrientation === 'portrait' }"
        :aria-pressed="currentOrientation === 'portrait'"
        :title="t('v2.modal.sheetPortrait')"
        data-test="sheet-orientation-portrait"
        @click="setOrientation('portrait')"
      >
        ▯
      </button>
      <button
        type="button"
        class="sheet-picker__chip"
        :class="{ active: currentOrientation === 'landscape' }"
        :aria-pressed="currentOrientation === 'landscape'"
        :title="t('v2.modal.sheetLandscape')"
        data-test="sheet-orientation-landscape"
        @click="setOrientation('landscape')"
      >
        ▭
      </button>
    </div>
  </div>
</template>

<style scoped>
.sheet-picker {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.sheet-picker__label {
  font-size: 0.75rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.sheet-picker__row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  align-items: center;
}
.sheet-picker__sep {
  color: #475569;
  margin: 0 0.15rem;
}
.sheet-picker__chip {
  border: 1px solid #334155;
  background: #1e293b;
  color: #cbd5e1;
  border-radius: 999px;
  padding: 0.2rem 0.6rem;
  font-size: 0.75rem;
  cursor: pointer;
  transition:
    background 0.12s ease,
    border-color 0.12s ease;
}
.sheet-picker__chip:hover {
  background: #334155;
}
.sheet-picker__chip.active {
  border-color: #059669;
  background: rgba(2, 44, 34, 0.6);
  color: #6ee7b7;
  font-weight: 600;
}
.sheet-picker__chip:focus-visible {
  outline: 2px solid #10b981;
  outline-offset: 2px;
}
</style>
