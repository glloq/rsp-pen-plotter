import { describe, expect, it } from 'vitest'
import { parseGcode } from './gcode'

const OPTIONS = {
  penUpCommand: 'M280 P0 S40',
  penDownCommand: 'M280 P0 S90',
  travelSpeedMmS: 100,
  defaultDrawSpeedMmS: 50,
}

describe('parseGcode', () => {
  it('separates drawing from travel and times each segment', () => {
    const gcode = [
      '; comment',
      'G21',
      'M280 P0 S40',
      'G0 X0 Y0',
      'M280 P0 S90',
      'G1 X60 Y0 F3000', // 60 mm at 50 mm/s -> 1.2 s drawing
      'M280 P0 S40',
    ].join('\n')

    const result = parseGcode(gcode, OPTIONS)
    expect(result.drawingTimeSeconds).toBeCloseTo(1.2, 3)
    expect(result.travelTimeSeconds).toBeGreaterThanOrEqual(0)
    expect(result.bounds).toEqual({ minX: 0, minY: 0, maxX: 60, maxY: 0 })
  })

  it('marks rapids with the pen down as travel, not drawing', () => {
    const gcode = ['M280 P0 S90', 'G0 X10 Y0', 'G1 X20 Y0 F600'].join('\n')
    const result = parseGcode(gcode, OPTIONS)
    const drawing = result.segments.filter((s) => s.drawing)
    expect(drawing).toHaveLength(1)
    expect(drawing[0]!.x1).toBe(20)
  })

  it('ignores comments and blank lines', () => {
    const result = parseGcode('; just a comment\n\n   \n', OPTIONS)
    expect(result.segments).toHaveLength(0)
    expect(result.totalTimeSeconds).toBe(0)
  })

  it('falls back to a unit bounding box when there is no geometry', () => {
    const result = parseGcode('M280 P0 S40\n', OPTIONS)
    expect(result.bounds).toEqual({ minX: 0, minY: 0, maxX: 1, maxY: 1 })
  })

  it('derives the layer colour from the label when color= is empty', () => {
    // Legacy G-code (or a backend that lost source_color across rerender)
    // emits the LAYER marker with no hex. The label still encodes the
    // palette colour for bitmap-derived layers, so the simulator should
    // pick that up instead of leaving every segment uncolourised.
    const gcode = [
      'M280 P0 S40',
      'G0 X0 Y0',
      '; LAYER label="color-ff0000" color= slot=',
      'M280 P0 S90',
      'G1 X10 Y0 F3000',
      'M280 P0 S40',
      '; LAYER label="placement-1__color-00aa00" color= slot=1',
      'M280 P0 S90',
      'G1 X20 Y0 F3000',
    ].join('\n')
    const result = parseGcode(gcode, OPTIONS)
    const drawing = result.segments.filter((s) => s.drawing)
    expect(drawing.map((s) => s.colorHex)).toEqual(['#ff0000', '#00aa00'])
    expect(result.colors.map((c) => c.hex).sort()).toEqual([
      '#00aa00',
      '#ff0000',
    ])
  })
})
