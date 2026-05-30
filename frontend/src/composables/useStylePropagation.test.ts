import { describe, expect, it } from 'vitest'
import { applyMasterStyleToLayers, type StylePropagationStore } from './useStylePropagation'

function makeStore(
  layers: { layer_id: string; source_color?: string; target_pen_slot?: number | null }[],
) {
  const calls: {
    layerId: string
    algorithm: string
    algorithm_options: Record<string, unknown>
  }[] = []
  const slotPatches: { layerId: string; slot: number | null | undefined }[] = []
  const store: StylePropagationStore = {
    layers,
    updateLayer(layerId, patch) {
      slotPatches.push({ layerId, slot: patch.target_pen_slot })
      const target = layers.find((l) => l.layer_id === layerId)
      if (target) target.target_pen_slot = patch.target_pen_slot
    },
    async applyLayerAlgorithm(layerId, algorithm, algorithm_options) {
      calls.push({ layerId, algorithm, algorithm_options })
    },
  }
  return { store, calls, slotPatches }
}

describe('applyMasterStyleToLayers', () => {
  it('multicolour master propagates colorRecipe per cluster', async () => {
    // ``color-crosshatch`` rotates hatch angle and tightens spacing per
    // cluster — exactly the per-cluster variation the multicolour path
    // used to drop on the floor.
    const { store, calls } = makeStore([
      { layer_id: 'color-ff0000', source_color: '#ff0000' },
      { layer_id: 'color-00ff00', source_color: '#00ff00' },
      { layer_id: 'color-0000ff', source_color: '#0000ff' },
    ])
    await applyMasterStyleToLayers(store, { styleId: 'color-crosshatch', penSlot: null })
    expect(calls).toHaveLength(3)
    // All crosshatch, but each with a distinct angle_deg.
    expect(calls.every((c) => c.algorithm === 'crosshatch')).toBe(true)
    const angles = calls.map((c) => c.algorithm_options.angle_deg)
    expect(new Set(angles).size).toBe(3)
  })

  it('monochrome master still uses bandRecipe (no regression)', async () => {
    const { store, calls } = makeStore([{ layer_id: 'color-111111' }, { layer_id: 'color-cccccc' }])
    // ``mono-crosshatch`` defines a bandRecipe; colorRecipe is undefined,
    // so the propagation falls through to bandRecipe as before.
    await applyMasterStyleToLayers(store, { styleId: 'mono-crosshatch', penSlot: 0 })
    expect(calls).toHaveLength(2)
    expect(calls.every((c) => c.algorithm === 'crosshatch')).toBe(true)
  })

  it('flat colour master uses defaultAlgorithm when colorRecipe returns null-equivalent', async () => {
    const { store, calls } = makeStore([
      { layer_id: 'color-aaaaaa', source_color: '#aaaaaa' },
      { layer_id: 'color-555555', source_color: '#555555' },
    ])
    await applyMasterStyleToLayers(store, { styleId: 'color-flat', penSlot: null })
    expect(calls).toHaveLength(2)
    expect(calls.every((c) => c.algorithm === 'direct')).toBe(true)
  })

  it('prefers the operator recipeResolver over the registry recipe', async () => {
    // Simulates the Style-tab sliders feeding ``monoRecipeForBand`` /
    // ``multicolorRecipeForCluster``: the resolver wins over the
    // registry's hardcoded recipe so the per-layer propagation matches
    // the live preview.
    const { store, calls } = makeStore([{ layer_id: 'color-111111' }, { layer_id: 'color-cccccc' }])
    await applyMasterStyleToLayers(store, {
      styleId: 'mono-crosshatch',
      penSlot: 0,
      recipeResolver: (index) => ({
        algorithm: 'stippling',
        algorithm_options: { density: 0.1 + index * 0.05 },
      }),
    })
    expect(calls).toHaveLength(2)
    expect(calls.every((c) => c.algorithm === 'stippling')).toBe(true)
    expect(calls[0]!.algorithm_options.density).toBe(0.1)
    expect(calls[1]!.algorithm_options.density).toBeCloseTo(0.15)
  })

  it('falls back to the registry recipe when the resolver returns null', async () => {
    // A freshly-added style without operator knobs returns null from the
    // resolver; the registry ``colorRecipe`` / ``bandRecipe`` then drives
    // the propagation exactly as before.
    const { store, calls } = makeStore([
      { layer_id: 'color-ff0000', source_color: '#ff0000' },
      { layer_id: 'color-00ff00', source_color: '#00ff00' },
      { layer_id: 'color-0000ff', source_color: '#0000ff' },
    ])
    await applyMasterStyleToLayers(store, {
      styleId: 'color-crosshatch',
      penSlot: null,
      recipeResolver: () => null,
    })
    expect(calls).toHaveLength(3)
    expect(calls.every((c) => c.algorithm === 'crosshatch')).toBe(true)
    const angles = calls.map((c) => c.algorithm_options.angle_deg)
    expect(new Set(angles).size).toBe(3)
  })

  it('assigns the requested pen slot before queuing the algorithm override', async () => {
    const { store, calls, slotPatches } = makeStore([
      { layer_id: 'color-000000', target_pen_slot: null },
    ])
    await applyMasterStyleToLayers(store, { styleId: 'mono-crosshatch', penSlot: 2 })
    expect(slotPatches).toEqual([{ layerId: 'color-000000', slot: 2 }])
    expect(calls).toHaveLength(1)
  })
})
