import { describe, expect, it } from 'vitest'
import { resolveEffectivePalette } from './effectivePalette'

// Pin the palette-source resolution rule so the StyleTab watch that
// drives the per-layer picker can't drift silently. Each branch of the
// three-way toggle gets its own test; the union branch covers the
// case-insensitive dedup so an operator who declared ``#FF0000`` on
// the inventory and ``#ff0000`` on the pen rack doesn't end up with
// two identical chips in the picker.

describe('resolveEffectivePalette', () => {
  it('returns only the installed pens when source is "pens"', () => {
    const result = resolveEffectivePalette('pens', ['#111', '#222'], ['#aaa', '#bbb'])
    expect(result).toEqual(['#111', '#222'])
  })

  it('returns only the inventory when source is "available"', () => {
    const result = resolveEffectivePalette('available', ['#111', '#222'], ['#aaa', '#bbb'])
    expect(result).toEqual(['#aaa', '#bbb'])
  })

  it('returns pens then inventory extras when source is "union"', () => {
    const result = resolveEffectivePalette(
      'union',
      ['#111111', '#222222'],
      ['#aaaaaa', '#bbbbbb'],
    )
    expect(result).toEqual(['#111111', '#222222', '#aaaaaa', '#bbbbbb'])
  })

  it('dedups the union case-insensitively so #FF0000 + #ff0000 collapse', () => {
    const result = resolveEffectivePalette(
      'union',
      ['#FF0000', '#00FF00'],
      ['#ff0000', '#0000FF'],
    )
    // Pens preserved verbatim; inventory contributes only the non-dup.
    expect(result).toEqual(['#FF0000', '#00FF00', '#0000FF'])
  })

  it('returns an empty array when both pools are empty', () => {
    expect(resolveEffectivePalette('pens', [], [])).toEqual([])
    expect(resolveEffectivePalette('available', [], [])).toEqual([])
    expect(resolveEffectivePalette('union', [], [])).toEqual([])
  })

  it('does not mutate the inputs (returns a fresh array)', () => {
    const pens = ['#111111']
    const inv = ['#aaaaaa']
    const result = resolveEffectivePalette('union', pens, inv)
    result.push('#bbbbbb')
    expect(pens).toEqual(['#111111'])
    expect(inv).toEqual(['#aaaaaa'])
  })
})
