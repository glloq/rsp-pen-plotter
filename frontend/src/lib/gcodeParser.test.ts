// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest'
import { parseGcodeMaybeAsync } from './gcodeParser'
import type { ParseOptions, SimResult } from './gcode'

// happy-dom doesn't define ``Worker`` (verified), so the client must take
// the synchronous main-thread branch: it returns a ``SimResult`` directly
// (not a Promise) so the playback ``reparse`` path stays synchronous for
// callers that read ``sim`` on the same tick.

const SAMPLE_GCODE = `G21
G90
G0 X0 Y0
M3 S1000
G1 X10 Y10 F1800
M3 S0
G0 X0 Y0
`

const PARSE_OPTIONS: ParseOptions = {
  penUpCommand: 'M3 S0',
  penDownCommand: 'M3 S1000',
  travelSpeedMmS: 80,
  defaultDrawSpeedMmS: 30,
  toolChangeCommand: 'M0',
}

describe('parseGcodeMaybeAsync (no Worker available)', () => {
  it('returns a SimResult synchronously rather than a Promise', () => {
    const out = parseGcodeMaybeAsync(SAMPLE_GCODE, PARSE_OPTIONS)
    expect(out).not.toBeInstanceOf(Promise)
    const result = out as SimResult
    expect(result.segments.length).toBeGreaterThan(0)
    expect(result.totalTimeSeconds).toBeGreaterThan(0)
  })
})
