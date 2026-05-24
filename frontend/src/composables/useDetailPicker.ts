// Single source of truth for the named "Detail" tiers that appear in
// both the Colors and Render tabs. The pixel values map to
// ``max_dimension_px`` on the backend (the longer side of the
// segmentation canvas) — higher tiers let fine features (text strokes,
// table grid lines, dense schematic detail) survive the segmentation
// pass instead of being smoothed away.
//
// The "Ultra" tier (4096) was added after the operator reported that
// "increasing detail doesn't do much" on text + table imagery: the
// previous Max (2400) was already the backend's silent ceiling, so the
// slider topped out before the operator could push detail further.
// The new tier matches the backend's expanded 8192 cap, leaving
// headroom for a future "Native" tier if needed.

import { computed, type Ref } from 'vue'

export type DetailId = 'low' | 'standard' | 'high' | 'max' | 'ultra'

export interface DetailLevel {
  id: DetailId
  value: number       // pixels — the longer side of the segmentation canvas
  labelKey: string    // i18n key resolved by consumers
}

export const DETAIL_LEVELS: readonly DetailLevel[] = [
  { id: 'low', value: 400, labelKey: 'mono.detailLow' },
  { id: 'standard', value: 800, labelKey: 'mono.detailStandard' },
  { id: 'high', value: 1600, labelKey: 'mono.detailHigh' },
  { id: 'max', value: 3200, labelKey: 'mono.detailMax' },
  { id: 'ultra', value: 4800, labelKey: 'mono.detailUltra' },
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
