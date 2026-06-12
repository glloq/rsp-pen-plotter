import { describe, expect, it } from 'vitest'
import { assignPoolHexes, nearestPoolHex } from './nearestColor'

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

// Mirrors the backend's ``auto_assign_layer_colors`` unique-while-possible
// greedy matching — regression suite for the >4-colour collapse where 6
// clusters against 6 pens piled onto the 2-3 nearest pens.
describe('assignPoolHexes', () => {
  it('keeps inks distinct while unused pool entries remain', () => {
    const items = [
      { sourceHex: '#1a1a1a' },
      { sourceHex: '#2a2a2a' }, // both greys nearest to #000000
      { sourceHex: '#d01010' },
      { sourceHex: '#e03030' }, // both reds nearest to #ff0000
      { sourceHex: '#1040d0' },
      { sourceHex: '#3060e0' }, // both blues nearest to #0000ff
    ]
    const pool = ['#000000', '#555555', '#ff0000', '#aa3333', '#0000ff', '#3355aa']
    const out = assignPoolHexes(items, pool)
    expect(out).not.toContain(null)
    expect(new Set(out).size).toBe(6)
  })

  it('reuses inks only once the pool is exhausted', () => {
    const items = [{ sourceHex: '#ff0000' }, { sourceHex: '#fa0505' }, { sourceHex: '#0000ff' }]
    const out = assignPoolHexes(items, ['#ff0000', '#0000ff'])
    expect(new Set(out)).toEqual(new Set(['#ff0000', '#0000ff']))
    // The blue cluster keeps the blue ink (never displaced by the reds).
    expect(out[2]).toBe('#0000ff')
  })

  it('pinned items consume their pool entry and stay untouched', () => {
    const items = [{ sourceHex: '#101010', pinnedHex: '#000000' }, { sourceHex: '#151515' }]
    const out = assignPoolHexes(items, ['#000000', '#333333'])
    expect(out[0]).toBeNull() // keep the pin
    expect(out[1]).toBe('#333333') // black is taken → next dark ink
  })

  it('duplicate pool entries allow that many uses', () => {
    const items = [{ sourceHex: '#0a0a0a' }, { sourceHex: '#111111' }]
    const out = assignPoolHexes(items, ['#000000', '#000000'])
    expect(out).toEqual(['#000000', '#000000'])
  })

  it('returns all nulls for an empty pool', () => {
    expect(assignPoolHexes([{ sourceHex: '#abcdef' }], [])).toEqual([null])
  })

  it('does not scatter close clusters onto far inks (ΔE threshold)', () => {
    // Three greens against a pool whose only green is #00aa00 used to be
    // forced onto black/blue to stay distinct (greens drawn as black/blue
    // in the preview). The two that can't get the green ink now reuse it.
    const items = [
      { sourceHex: '#1f6f3f' },
      { sourceHex: '#2e8b57' },
      { sourceHex: '#3cb371' },
      { sourceHex: '#c0392b' },
    ]
    const out = assignPoolHexes(items, ['#000000', '#ff0000', '#0000ff', '#00aa00'])
    expect(out).toEqual(['#00aa00', '#00aa00', '#00aa00', '#ff0000'])
  })

  it('still spreads when the distinct match stays perceptually close', () => {
    const items = [{ sourceHex: '#1f3fa0' }, { sourceHex: '#3f6fd0' }]
    const out = assignPoolHexes(items, ['#0000ff', '#3366cc'])
    expect(out).toEqual(['#0000ff', '#3366cc'])
  })
})
