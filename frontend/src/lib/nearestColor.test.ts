import { describe, expect, it } from 'vitest'
import { assignPoolHexes, chooseInkPalette, nearestPoolHex } from './nearestColor'

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
  it('maps genuinely distinct colours to their own inks', () => {
    // Nearest-match already yields N distinct inks when the pool spans
    // the image's colours — no distinct-forcing needed.
    const items = [
      { sourceHex: '#e03030' },
      { sourceHex: '#30c030' },
      { sourceHex: '#3030e0' },
      { sourceHex: '#e0e030' },
      { sourceHex: '#e030e0' },
      { sourceHex: '#30e0e0' },
    ]
    const pool = ['#ff0000', '#00c000', '#0000ff', '#ffff00', '#ff00ff', '#00ffff']
    const out = assignPoolHexes(items, pool)
    expect(out).not.toContain(null)
    expect(new Set(out).size).toBe(6)
  })

  it('close clusters share the same ink instead of being scattered', () => {
    const items = [{ sourceHex: '#ff0000' }, { sourceHex: '#fa0505' }, { sourceHex: '#0000ff' }]
    const out = assignPoolHexes(items, ['#ff0000', '#0000ff'])
    // Both reds take the red ink (merged downstream); blue takes blue.
    expect(out).toEqual(['#ff0000', '#ff0000', '#0000ff'])
  })

  it('pinned items stay untouched; auto rows take their nearest', () => {
    const items = [{ sourceHex: '#101010', pinnedHex: '#000000' }, { sourceHex: '#151515' }]
    const out = assignPoolHexes(items, ['#000000', '#333333'])
    expect(out[0]).toBeNull() // keep the pin
    expect(out[1]).toBe('#000000') // nearest ink (reuse allowed)
  })

  it('duplicate pool entries allow that many uses', () => {
    const items = [{ sourceHex: '#0a0a0a' }, { sourceHex: '#111111' }]
    const out = assignPoolHexes(items, ['#000000', '#000000'])
    expect(out).toEqual(['#000000', '#000000'])
  })

  it('returns all nulls for an empty pool', () => {
    expect(assignPoolHexes([{ sourceHex: '#abcdef' }], [])).toEqual([null])
  })

  it('does not scatter close clusters onto far inks', () => {
    // Three greens against a pool whose only green is #00aa00 used to be
    // forced onto black/blue to stay distinct (greens drawn as black/blue
    // in the preview). Nearest-match keeps all three on the green.
    const items = [
      { sourceHex: '#1f6f3f' },
      { sourceHex: '#2e8b57' },
      { sourceHex: '#3cb371' },
      { sourceHex: '#c0392b' },
    ]
    const out = assignPoolHexes(items, ['#000000', '#ff0000', '#0000ff', '#00aa00'])
    expect(out).toEqual(['#00aa00', '#00aa00', '#00aa00', '#ff0000'])
  })
})

describe('chooseInkPalette', () => {
  const pool = ['#111111', '#22aa55', '#1e3cc8', '#c81e1e', '#808080']

  it('returns one ink per centroid when m >= the number of centroids', () => {
    const out = chooseInkPalette(['#2e8b57', '#1e3cc8'], pool, 5)
    expect(out).toEqual(['#22aa55', '#1e3cc8'])
  })

  it('reduces N centroids to M inks by merging the closest in Lab', () => {
    // Four centroids: two greens, a blue, a grey. Asking for 3 colours merges
    // the two greens into one green ink — grey stays grey, blue stays blue.
    const centroids = ['#2e8b57', '#3cb371', '#1e3cc8', '#808080']
    const out = chooseInkPalette(centroids, pool, 3)
    expect(out).toHaveLength(3)
    expect(out).toContain('#22aa55') // green
    expect(out).toContain('#1e3cc8') // blue
    expect(out).toContain('#808080') // grey — never flips to another hue
  })

  it('collapses everything onto one ink at m = 1', () => {
    const out = chooseInkPalette(['#2e8b57', '#1e3cc8', '#808080'], pool, 1)
    expect(out).toHaveLength(1)
  })

  it('returns [] for an empty pool or no centroids', () => {
    expect(chooseInkPalette(['#123456'], [], 3)).toEqual([])
    expect(chooseInkPalette([], pool, 3)).toEqual([])
  })
})
