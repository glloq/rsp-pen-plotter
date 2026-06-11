import { describe, expect, it } from 'vitest'
import { PALETTE_PAD_COLORS, nextPadColor, rec709Luminance, uniquePalette } from './paletteColors'

describe('nextPadColor', () => {
  it('starts with grey on an empty palette (legacy default)', () => {
    expect(nextPadColor([])).toBe('#888888')
  })

  it('never duplicates an existing chip', () => {
    // Regression for the >4-colour collapse: growing the palette used to
    // append ``#888888`` repeatedly, so the new chips merged into a
    // single rendered layer.
    const palette: string[] = ['#888888', '#000000']
    for (let i = 0; i < 10; i++) palette.push(nextPadColor(palette))
    expect(new Set(palette.map((h) => h.toLowerCase())).size).toBe(palette.length)
  })

  it('is case-insensitive when checking existing chips', () => {
    expect(nextPadColor(['#888888'.toUpperCase()])).not.toBe('#888888')
  })

  it('keeps every pad colour below the kmeans drop-background threshold', () => {
    // A freshly-padded chip must never silently vanish as "paper".
    for (const hex of PALETTE_PAD_COLORS) {
      expect(rec709Luminance(hex), hex).toBeLessThan(0.85)
    }
  })
})

describe('uniquePalette', () => {
  it('drops case-insensitive duplicates, keeping first occurrences', () => {
    expect(uniquePalette(['#FF0000', '#ff0000', '#00ff00'])).toEqual(['#FF0000', '#00ff00'])
  })

  it('passes a distinct palette through unchanged', () => {
    expect(uniquePalette(['#111111', '#222222'])).toEqual(['#111111', '#222222'])
  })
})

describe('rec709Luminance', () => {
  it('matches the backend plain weighted sum (no gamma)', () => {
    expect(rec709Luminance('#000000')).toBe(0)
    expect(rec709Luminance('#ffffff')).toBeCloseTo(1)
    // Pure green carries the 0.7152 weight.
    expect(rec709Luminance('#00ff00')).toBeCloseTo(0.7152)
  })
})
