// Post-/upload propagation of a master style across the produced
// layers. Extracted from SourceSection.vue's inline loop
// (originally lines 579-596) so:
//   - the per-band recipe lookup goes through the registry's canonical
//     ``bandRecipe`` rather than the legacy ``MonoMode.algoForBand``
//   - the same propagation can be re-triggered from the Render tab
//     when the operator changes the master style after upload, without
//     duplicating the loop body
//   - the pen-slot assignment + recipe-application are pinned in one
//     place so future bulk-by-pen / bulk-by-style operations can reuse
//     the helper instead of reimplementing the iteration
//
// The composable is intentionally I/O-light: it takes a store
// reference and a master style id, walks the layers, calls
// ``updateLayer`` for the slot assignment, and queues
// ``applyLayerAlgorithm`` calls — the store already debounces /rerender
// so calling it once per band only fires one round-trip.

import { resolveMasterStyle } from '../data/printRegistry'

// Minimal store surface the composable needs. Avoids importing the
// concrete pinia store so this file stays trivial to unit test.
export interface StylePropagationStore {
  layers: ReadonlyArray<{
    layer_id: string
    target_pen_slot?: number | null
    // Cluster hex (``#rrggbb``) for multicolour master styles whose
    // ``colorRecipe`` branches on hue (CMYK halftone angles, complement
    // crosshatch, etc.). Optional so legacy callers / tests can hand in
    // bare layers without breaking the contract.
    source_color?: string
  }>
  updateLayer: (layerId: string, patch: { target_pen_slot?: number | null }) => void
  applyLayerAlgorithm: (
    layerId: string,
    algorithm: string,
    algorithmOptions: Record<string, unknown>,
  ) => Promise<void>
}

export interface PropagationOptions {
  // Master style id to apply. Passed through ``resolveMasterStyle`` so
  // legacy ids and unknown ids both end up on the default master.
  styleId: string | null | undefined
  // When provided, every produced layer is reassigned to this pen
  // slot before its algorithm override is queued — mirrors the
  // "mono ink slot" pre-assignment SourceSection does today so the
  // operator doesn't see the manual-swap warning for an N-band image
  // they want to print with one pen.
  penSlot?: number | null
  // Operator-tuned recipe resolver. When provided, it takes precedence
  // over the registry's hardcoded ``colorRecipe`` / ``bandRecipe`` so
  // the per-layer propagation reflects the *live* Style-tab sliders
  // (spacing / density / angle ranges, per-band pins, …) rather than
  // the style's factory defaults. Returns null to fall back to the
  // registry recipe for that layer — that's how a freshly-added style
  // without operator knobs still propagates via the legacy contract.
  // ``index``/``total``/``hex`` mirror the registry recipe signature so
  // the same darkest-first ordering and hue branching apply.
  recipeResolver?: (
    index: number,
    total: number,
    hex: string,
  ) => { algorithm: string; algorithm_options: Record<string, unknown> } | null
}

// Apply a master style's per-band recipe to every layer currently in
// the store. Returns the number of layers that received an override
// (handy for surfacing toasts like "Reset 5 overrides"); 0 means the
// store had no layers, not that nothing changed.
//
// Calls into the store are sequenced because ``applyLayerAlgorithm``
// is async — but the store debounces /rerender internally, so the
// final round-trip carries every override at once.
export async function applyMasterStyleToLayers(
  store: StylePropagationStore,
  options: PropagationOptions,
): Promise<number> {
  const layers = store.layers
  if (!layers.length) return 0
  const style = resolveMasterStyle(options.styleId)
  const total = layers.length
  let applied = 0

  for (let i = 0; i < total; i++) {
    const layer = layers[i]!
    if (
      options.penSlot !== undefined &&
      options.penSlot !== null &&
      layer.target_pen_slot !== options.penSlot
    ) {
      store.updateLayer(layer.layer_id, { target_pen_slot: options.penSlot })
    }
    // Resolution order, most → least specific:
    //   1. operator-tuned ``recipeResolver`` (live Style-tab sliders) —
    //      so what the picker would render and what the layers get stay
    //      in lockstep for every style.
    //   2. multicolour ``colorRecipe`` — branches on the cluster hex
    //      (e.g. CMYK halftone picks an angle per ink).
    //   3. mono ``bandRecipe`` — keyed only by the band index.
    //   4. the style's flat default.
    // Steps 2-4 are the registry fallback the resolver returns null to
    // defer to, so single-recipe styles and dual-mode helpers keep
    // working untouched.
    const hex = layer.source_color ?? '#000000'
    const recipe = options.recipeResolver?.(i, total, hex) ??
      style.colorRecipe?.(i, total, hex) ??
      style.bandRecipe?.(i, total) ?? {
        algorithm: style.defaultAlgorithm,
        algorithm_options: { ...style.defaultAlgorithmOptions },
      }
    await store.applyLayerAlgorithm(layer.layer_id, recipe.algorithm, recipe.algorithm_options)
    applied += 1
  }
  return applied
}
