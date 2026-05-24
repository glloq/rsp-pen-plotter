// Single source of truth for the named "Detail" tiers
// (Low/Standard/High/Max) that appear in both the Colors and Render
// tabs. The four pixel values map to ``max_dimension_px`` on the
// backend (the longer side of the segmentation canvas), and the
// vocabulary stays consistent across print modes so the operator can
// build muscle memory regardless of which tab they're in.
//
// Used by both SegmentationCard (multicolour) and MonochromeCard
// (monochrome) — previously these two cards each carried their own
// copy of the tier table and the ``currentDetail`` resolver, which
// drifted apart silently. This composable is the deduplication.

import { computed, type Ref } from 'vue'

export type DetailId = 'low' | 'standard' | 'high' | 'max'

export interface DetailLevel {
  id: DetailId
  value: number       // pixels — the longer side of the segmentation canvas
  labelKey: string    // i18n key resolved by consumers
}

export const DETAIL_LEVELS: readonly DetailLevel[] = [
  { id: 'low', value: 400, labelKey: 'mono.detailLow' },
  { id: 'standard', value: 800, labelKey: 'mono.detailStandard' },
  { id: 'high', value: 1400, labelKey: 'mono.detailHigh' },
  { id: 'max', value: 2400, labelKey: 'mono.detailMax' },
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
