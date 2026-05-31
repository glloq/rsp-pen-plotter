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

  it('tessellates G2 / G3 arcs into drawing chords', () => {
    // A G3 (CCW) quarter circle of radius 10 from (10, 0) to (0, 10)
    // around centre (0, 0). Without arc support these would be
    // silently skipped, leaving Hershey letters with curved strokes
    // (e / a / c / o / d) reduced to disconnected straight skeletons.
    const gcode = [
      'M280 P0 S90', // pen down so the arc counts as drawing
      'G1 X10 Y0 F3000', // move to arc start
      'G3 X0 Y10 I-10 J0 F3000', // CCW quarter arc, centre at (0,0)
    ].join('\n')

    const result = parseGcode(gcode, OPTIONS)
    const drawing = result.segments.filter((s) => s.drawing)
    // 1 straight chord + arc tessellated to multiple chords.
    expect(drawing.length).toBeGreaterThan(2)

    // Every arc chord endpoint must sit on the circle of radius 10.
    const arcChords = drawing.slice(1)
    for (const seg of arcChords) {
      expect(Math.hypot(seg.x1, seg.y1)).toBeCloseTo(10, 1)
    }

    // Final chord lands exactly on the commanded end point so chained
    // moves don't drift due to floating-point round-off.
    const last = arcChords[arcChords.length - 1]!
    expect(last.x1).toBeCloseTo(0, 6)
    expect(last.y1).toBeCloseTo(10, 6)

    // Bounds must cover the arc, not just the chord endpoints — the
    // simulator's auto-fit zoom relies on this.
    expect(result.bounds.maxX).toBeCloseTo(10, 1)
    expect(result.bounds.maxY).toBeCloseTo(10, 1)
  })

  it('respects sweep direction: G2 clockwise vs G3 counter-clockwise', () => {
    // Same start / end / centre, opposite direction: G2 takes the long
    // way (3/4 turn), G3 takes the short way (1/4 turn). Verifying the
    // sweep accounting catches a sign-flip regression.
    const cw = parseGcode(
      ['M280 P0 S90', 'G1 X10 Y0', 'G2 X0 Y10 I-10 J0 F3000'].join('\n'),
      OPTIONS,
    )
    const ccw = parseGcode(
      ['M280 P0 S90', 'G1 X10 Y0', 'G3 X0 Y10 I-10 J0 F3000'].join('\n'),
      OPTIONS,
    )
    // Drawing time is proportional to arc length at the same feed rate.
    expect(cw.drawingTimeSeconds).toBeGreaterThan(ccw.drawingTimeSeconds * 2)
    // CW long-way arc dips into negative X / negative Y; CCW short-way
    // stays in the first quadrant.
    expect(cw.bounds.minX).toBeLessThan(-5)
    expect(cw.bounds.minY).toBeLessThan(-5)
    expect(ccw.bounds.minX).toBeGreaterThanOrEqual(0)
    expect(ccw.bounds.minY).toBeGreaterThanOrEqual(0)
  })
})
