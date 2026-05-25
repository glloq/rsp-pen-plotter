import { describe, expect, it } from 'vitest'
import { nearestPoolHex } from './nearestColor'

// Pins the ΔE 2000 nearest-match used by the LayerCard's
// "↻ reset to auto" affordance. The numeric path mirrors the backend's
// ``nearest_pool_hex`` so re-snapping client-side stays in lock-step
// with what the upload pipeline computed.

describe('nearestPoolHex', () => {
  it('returns the closest red when the source is nearly red', () => {
    expect(nearestPoolHex('#fa0202', ['#00ff00', '#ff0000', '#0000ff'])).toBe('#ff0000')
  })

  it('returns null when the pool is empty', () => {
    expect(nearestPoolHex('#abcdef', [])).toBeNull()
  })

  it('canonicalises shorthand hex to #rrggbb', () => {
    expect(nearestPoolHex('#fff', ['#FFF'])).toBe('#ffffff')
  })

  it('picks correctly across a varied pool', () => {
    const pool = ['#000000', '#ffffff', '#ff0000', '#00ff00', '#0000ff']
    expect(nearestPoolHex('#000001', pool)).toBe('#000000')
    expect(nearestPoolHex('#fefefe', pool)).toBe('#ffffff')
    expect(nearestPoolHex('#00ff10', pool)).toBe('#00ff00')
  })
})
