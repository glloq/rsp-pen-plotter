// @vitest-environment happy-dom
import { describe, expect, it, beforeEach } from 'vitest'
import { getDurationEstimateMs, recordDuration } from './durationEstimator'

describe('durationEstimator', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns 0 when no sample has been recorded', () => {
    expect(getDurationEstimateMs('generate')).toBe(0)
  })

  it('seeds with the first sample then blends subsequent ones via EMA', () => {
    recordDuration('generate', 10_000)
    expect(getDurationEstimateMs('generate')).toBe(10_000)
    // EMA with alpha 0.4: 10000*0.6 + 20000*0.4 = 14000
    recordDuration('generate', 20_000)
    expect(getDurationEstimateMs('generate')).toBe(14_000)
  })

  it('keeps separate estimates per key', () => {
    recordDuration('generate', 5_000)
    recordDuration('systemUpdate', 200_000)
    expect(getDurationEstimateMs('generate')).toBe(5_000)
    expect(getDurationEstimateMs('systemUpdate')).toBe(200_000)
  })

  it('ignores implausibly short or non-finite samples', () => {
    recordDuration('generate', 50)
    recordDuration('generate', Number.NaN)
    expect(getDurationEstimateMs('generate')).toBe(0)
  })

  it('persists across reloads (survives a fresh module read of localStorage)', () => {
    recordDuration('generate', 8_000)
    // Simulate a reload: the helper re-reads localStorage on every call.
    expect(getDurationEstimateMs('generate')).toBe(8_000)
  })
})
