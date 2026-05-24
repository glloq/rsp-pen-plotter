// Thin wrapper around the print registry's per-band recipe lookup so
// callers don't have to thread ``getStyle(id)?.bandRecipe?.(...)``
// chains by hand. Also bridges legacy mono-mode ids to their renamed
// registry equivalents.
//
// Used by useStylePropagation when applying per-band overrides post
// upload, and by future MasterStyleParams panels that want to preview
// what each band will look like before committing.

import {
  resolveMasterStyle,
  type BandRecipe,
  type PrintStyle,
} from '../data/printRegistry'

export interface UseMonoRecipe {
  style: PrintStyle
  // Returns null if the style doesn't carry a per-band recipe (binary
  // master modes, layer styles). Callers should fall back to the
  // style's ``defaultAlgorithm`` + ``defaultAlgorithmOptions`` in
  // that case.
  recipeFor: (bandIndex: number, totalBands: number) => BandRecipe | null
  hasPerBandRecipe: boolean
}

export function useMonoRecipe(styleId: string | null | undefined): UseMonoRecipe {
  const style = resolveMasterStyle(styleId)
  const hasPerBandRecipe = typeof style.bandRecipe === 'function'
  return {
    style,
    recipeFor: (i, total) => style.bandRecipe?.(i, total) ?? null,
    hasPerBandRecipe,
  }
}

// Convenience: pre-compute the recipe for every band in one go.
// Useful when generating preview thumbnails or showing the operator
// what each band of an N-band image will draw.
export function recipesForBands(
  styleId: string | null | undefined,
  totalBands: number,
): (BandRecipe | null)[] {
  const { recipeFor } = useMonoRecipe(styleId)
  return Array.from({ length: totalBands }, (_, i) => recipeFor(i, totalBands))
}
