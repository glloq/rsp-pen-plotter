import { describe, expect, it } from 'vitest'

import {
  computeLayerColorOpacityMap,
  computeLayerOpacityMap,
  type ColorOpacityLayer,
  type OpacityLayer,
} from './useEditorPreviewSvgEffects'

// The DOM walk itself needs real layout (getBoundingClientRect) which
// happy-dom can't provide, so the unit-testable core is the opacity map:
// hidden → 0, visible → clamped opacity_percent / 100. The "unknown group →
// 1.0" reset lives in the walk and is covered by EditPreviewPane.test.ts.

describe('computeLayerOpacityMap', () => {
  const layers: OpacityLayer[] = [
    { layer_id: 'color-aabbcc', opacity_percent: 100 },
    { layer_id: 'color-112233', opacity_percent: 40 },
    { layer_id: 'color-noPct' },
  ]

  it('maps a visible full-opacity layer to 1', () => {
    const map = computeLayerOpacityMap(layers, () => true)
    expect(map.get('color-aabbcc')).toBe(1)
  })

  it('scales a visible partial-opacity layer into 0..1', () => {
    const map = computeLayerOpacityMap(layers, () => true)
    expect(map.get('color-112233')).toBeCloseTo(0.4)
  })

  it('defaults a missing opacity_percent to fully opaque', () => {
    const map = computeLayerOpacityMap(layers, () => true)
    expect(map.get('color-noPct')).toBe(1)
  })

  it('collapses a hidden layer to 0 regardless of its opacity_percent', () => {
    const map = computeLayerOpacityMap(layers, (id) => id !== 'color-aabbcc')
    expect(map.get('color-aabbcc')).toBe(0)
    // The other layers stay visible.
    expect(map.get('color-112233')).toBeCloseTo(0.4)
  })

  it('clamps out-of-range opacity_percent values to 0..1', () => {
    const map = computeLayerOpacityMap(
      [
        { layer_id: 'over', opacity_percent: 250 },
        { layer_id: 'under', opacity_percent: -30 },
      ],
      () => true,
    )
    expect(map.get('over')).toBe(1)
    expect(map.get('under')).toBe(0)
  })
})

// Colour-keyed opacity map: how the EXPERT raw /preview (groups labelled by
// fill colour, not by layer_id) gets its eye-toggle visibility. Keys are
// lowercased; both source + assigned hexes resolve to the layer's opacity.
describe('computeLayerColorOpacityMap', () => {
  const layers: ColorOpacityLayer[] = [
    { layer_id: 'color-1e1edc', source_color: '#1E1EDC', assigned_color_hex: '#f5c518' },
    { layer_id: 'color-dc1e1e', source_color: '#dc1e1e', assigned_color_hex: null },
  ]

  it('maps a layer source colour (lowercased) to its visibility', () => {
    const hidden = new Set(['color-1e1edc'])
    const map = computeLayerColorOpacityMap(layers, (id) => !hidden.has(id))
    // Hidden layer collapses to 0 — keyed by its centroid (source) colour, the
    // way the flat preview group is filled.
    expect(map.get('#1e1edc')).toBe(0)
    // The other layer stays visible.
    expect(map.get('#dc1e1e')).toBe(1)
  })

  it('also keys the recoloured (assigned) ink so a snapped preview still hides', () => {
    const map = computeLayerColorOpacityMap(layers, () => false)
    expect(map.get('#f5c518')).toBe(0)
  })

  it('within a layer, the source colour is written last (wins its own fields)', () => {
    // A single layer whose assigned ink differs from its centroid: both keys
    // resolve to the SAME visibility, and the source key reflects the final
    // write. Hidden → both 0.
    const one: ColorOpacityLayer[] = [
      { layer_id: 'color-111111', source_color: '#111111', assigned_color_hex: '#222222' },
    ]
    const map = computeLayerColorOpacityMap(one, () => false)
    expect(map.get('#111111')).toBe(0)
    expect(map.get('#222222')).toBe(0)
  })
})
