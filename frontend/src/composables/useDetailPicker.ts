// Single source of truth for the named "Detail" tiers that appear in
// both the Colors and Render tabs. The pixel values map to
// ``max_dimension_px`` on the backend (the longer side of the
// segmentation canvas) — higher tiers let fine features (text strokes,
// table grid lines, dense schematic detail) survive the segmentation
// pass instead of being smoothed away.
//
// The "Ultra" tier (8192) matches the backend's expanded cap. Tier
// values double from one step to the next so the visual difference is
// obvious in the preview — the previous 1600/3200 spread between
// High and Max was too small for the downstream algorithms to expose
// any real change, and operators reported the picker felt broken.
// The chunked-argmin fix in segmentation.fixed_palette makes the
// 8192 ceiling actually usable; before, Ultra would 400.

import { computed, type Ref } from 'vue'

export type DetailId = 'low' | 'standard' | 'high' | 'max' | 'ultra'

export interface DetailLevel {
  id: DetailId
  value: number // pixels — the longer side of the segmentation canvas
  labelKey: string // i18n key resolved by consumers
}

export const DETAIL_LEVELS: readonly DetailLevel[] = [
  { id: 'low', value: 600, labelKey: 'mono.detailLow' },
  { id: 'standard', value: 1200, labelKey: 'mono.detailStandard' },
  { id: 'high', value: 2400, labelKey: 'mono.detailHigh' },
  { id: 'max', value: 4800, labelKey: 'mono.detailMax' },
  { id: 'ultra', value: 8192, labelKey: 'mono.detailUltra' },
]

// Map an arbitrary ``max_dimension_px`` to the closest tier id. Used to
// highlight the active tier button in the UI when the value was loaded
// from a persisted placement that may not sit exactly on one of the
// canonical 400/800/1400/2400 pixel marks.
export function tierFor(value: number): DetailId {
  let best = DETAIL_LEVELS[0]!
  let bestDelta = Math.abs(best.value - value)
  for (const level of DETAIL_LEVELS.slice(1)) {
    const delta = Math.abs(level.value - value)
    if (delta < bestDelta) {
      best = level
      bestDelta = delta
    }
  }
  return best.id
}

// Reactive helper for components. Accepts a ref-like to the underlying
// ``max_dimension_px`` field; exposes the active tier id and a setter
// that writes the canonical pixel value back. Consumers wire the
// setter into the tier button click handler and the active tier into
// the highlight class.
export function useDetailPicker(maxDimensionPx: Ref<number>) {
  const currentDetail = computed<DetailId>(() => tierFor(maxDimensionPx.value))

  function setDetail(id: DetailId): void {
    const level = DETAIL_LEVELS.find((l) => l.id === id)
    if (level) maxDimensionPx.value = level.value
  }

  function setDetailValue(value: number): void {
    maxDimensionPx.value = value
  }

  return {
    detailLevels: DETAIL_LEVELS,
    currentDetail,
    setDetail,
    setDetailValue,
  }
}
