// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest'
import {
  applyPhysicalStrokeWidth,
  canonicalHex,
  layerStrokeWidthsPx,
  mmPerViewBoxUnit,
  parsePenWidthMm,
  strokeWidthMmByHex,
} from './penWidth'

describe('canonicalHex', () => {
  it('expands shorthand and lowercases', () => {
    expect(canonicalHex('#ABC')).toBe('#aabbcc')
    expect(canonicalHex('FF0000')).toBe('#ff0000')
  })
})

describe('parsePenWidthMm', () => {
  it('accepts a dot or a comma decimal separator', () => {
    expect(parsePenWidthMm('0.8')).toBe(0.8)
    expect(parsePenWidthMm('0,8')).toBe(0.8)
    expect(parsePenWidthMm('.8')).toBe(0.8)
  })

  it('tolerates a trailing unit and surrounding spaces', () => {
    // Regression: the UI shows "mm" next to the field, so operators type
    // "0.8mm" / "0,8 mm"; the old parser returned null and the save
    // silently fell back to 0.5, so the diameter appeared stuck.
    expect(parsePenWidthMm('0.8mm')).toBe(0.8)
    expect(parsePenWidthMm('0,8 mm')).toBe(0.8)
    expect(parsePenWidthMm(' 0.8 ')).toBe(0.8)
    expect(parsePenWidthMm('12,5 mm')).toBe(12.5)
  })

  it('passes through a finite positive number', () => {
    expect(parsePenWidthMm(0.5)).toBe(0.5)
  })

  it('rejects non-positive, empty, or non-numeric input', () => {
    expect(parsePenWidthMm('0')).toBeNull()
    expect(parsePenWidthMm('-1')).toBeNull()
    expect(parsePenWidthMm('')).toBeNull()
    expect(parsePenWidthMm('abc')).toBeNull()
    expect(parsePenWidthMm(0)).toBeNull()
  })
})

describe('strokeWidthMmByHex', () => {
  it('keys widths by canonical hex and drops non-positive values', () => {
    const map = strokeWidthMmByHex([
      { hex: '#F00', stroke_width_mm: 0.8 },
      { hex: '#00ff00', stroke_width_mm: 0 },
    ])
    expect(map.get('#ff0000')).toBe(0.8)
    expect(map.has('#00ff00')).toBe(false)
  })
})

describe('mmPerViewBoxUnit', () => {
  it('returns the geometric-mean mm per viewBox unit', () => {
    // 100 mm wide over a 200-unit viewBox → 0.5 mm/unit on both axes.
    const svg = '<svg viewBox="0 0 200 100" width="200" height="100"></svg>'
    expect(mmPerViewBoxUnit(svg, 100, 50)).toBeCloseTo(0.5, 6)
  })

  it('returns null when the viewBox is missing or degenerate', () => {
    expect(mmPerViewBoxUnit('<svg></svg>', 100, 100)).toBeNull()
    expect(mmPerViewBoxUnit('<svg viewBox="0 0 0 0"></svg>', 100, 100)).toBeNull()
  })
})

describe('applyPhysicalStrokeWidth', () => {
  const svg =
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">' +
    '<g stroke="#ff0000" fill="none" stroke-width="0.8"><line x1="0" y1="0" x2="9" y2="9"/></g>' +
    '<g stroke="#0000ff" fill="none" stroke-width="0.8"><line x1="0" y1="0" x2="9" y2="9"/></g>' +
    '</svg>'

  it('re-strokes matched colours to mm / mmPerUnit and leaves others', () => {
    // Red pen = 1.0 mm, scale 0.5 mm/unit → 2.0 user units. Blue is not
    // declared, so it keeps the algorithm's 0.8.
    const map = new Map<string, number>([['#ff0000', 1.0]])
    const out = applyPhysicalStrokeWidth(svg, map, 0.5)
    expect(out).toContain('stroke="#ff0000"')
    expect(out).toMatch(
      /stroke="#ff0000"[^>]*stroke-width="2(\.0+)?"|stroke-width="2(\.0+)?"[^>]*stroke="#ff0000"/,
    )
    // Blue group untouched (still 0.8).
    const blue = out.slice(out.indexOf('#0000ff'))
    expect(blue).toContain('0.8')
  })

  it('returns the input unchanged when nothing matches or scale invalid', () => {
    const empty = new Map<string, number>()
    expect(applyPhysicalStrokeWidth(svg, empty, 0.5)).toBe(svg)
    const map = new Map<string, number>([['#ff0000', 1.0]])
    expect(applyPhysicalStrokeWidth(svg, map, 0)).toBe(svg)
  })
})

describe('layerStrokeWidthsPx', () => {
  const layers = [
    { layer_id: 'color-ff0000', source_color: '#ff0000', assigned_color_hex: null },
    { layer_id: 'color-00ff00', source_color: '#00ff00', assigned_color_hex: '#0000ff' },
    { layer_id: 'color-undeclared', source_color: '#abcdef', assigned_color_hex: null },
  ]

  it('maps declared colours to mm / mmPerUnit, prefers assigned, skips others', () => {
    const map = new Map<string, number>([
      ['#ff0000', 1.0],
      ['#0000ff', 2.0],
    ])
    // mmPerUnit 0.5 → red 1.0/0.5 = 2.0, assigned blue 2.0/0.5 = 4.0.
    const out = layerStrokeWidthsPx(layers, map, 0.5)
    expect(out).toEqual({ 'color-ff0000': 2.0, 'color-00ff00': 4.0 })
    expect(out['color-undeclared']).toBeUndefined()
  })

  it('is empty when scale invalid or inventory empty', () => {
    expect(layerStrokeWidthsPx(layers, new Map(), 0.5)).toEqual({})
    expect(layerStrokeWidthsPx(layers, new Map([['#ff0000', 1]]), 0)).toEqual({})
  })
})
