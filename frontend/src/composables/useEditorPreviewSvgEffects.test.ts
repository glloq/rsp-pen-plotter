import { describe, expect, it } from 'vitest'

import { computeLayerOpacityMap, type OpacityLayer } from './useEditorPreviewSvgEffects'

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
