import { describe, expect, it } from 'vitest'
import {
  estimatedPercent,
  formatDuration,
  remainingSeconds,
  PROGRESS_CEILING_PCT,
  PROGRESS_HEAD_START_PCT,
} from './progressEstimate'

describe('estimatedPercent', () => {
  it('starts at the head start and grows monotonically toward the estimate', () => {
    const at0 = estimatedPercent(0, 1000)
    const at500 = estimatedPercent(500, 1000)
    const at1000 = estimatedPercent(1000, 1000)
    expect(at0).toBe(PROGRESS_HEAD_START_PCT)
    expect(at500).toBeGreaterThan(at0)
    expect(at1000).toBeGreaterThan(at500)
    // ~80 % once the estimate elapses.
    expect(at1000).toBeGreaterThanOrEqual(70)
    expect(at1000).toBeLessThanOrEqual(85)
  })

  it('never reaches 100 %, even far past the estimate', () => {
    const overrun = estimatedPercent(100_000, 200)
    expect(overrun).toBeLessThan(100)
    expect(overrun).toBeLessThanOrEqual(PROGRESS_CEILING_PCT)
    expect(overrun).toBeGreaterThanOrEqual(90)
  })

  it('falls back to the head start for a non-positive or non-finite estimate', () => {
    expect(estimatedPercent(500, 0)).toBe(PROGRESS_HEAD_START_PCT)
    expect(estimatedPercent(500, -1)).toBe(PROGRESS_HEAD_START_PCT)
    expect(estimatedPercent(500, Number.NaN)).toBe(PROGRESS_HEAD_START_PCT)
  })

  it('honours custom curve bounds', () => {
    expect(estimatedPercent(0, 1000, { headStart: 20 })).toBe(20)
    expect(estimatedPercent(100_000, 200, { ceiling: 95 })).toBeLessThanOrEqual(95)
  })
})

describe('remainingSeconds', () => {
  it('counts down whole seconds until the estimate elapses', () => {
    expect(remainingSeconds(0, 10_000)).toBe(10)
    expect(remainingSeconds(7_200, 10_000)).toBe(3)
  })

  it('returns null once the estimate is overrun (unknown remaining)', () => {
    expect(remainingSeconds(10_000, 10_000)).toBeNull()
    expect(remainingSeconds(12_000, 10_000)).toBeNull()
  })

  it('returns null when there is no usable estimate', () => {
    expect(remainingSeconds(500, 0)).toBeNull()
    expect(remainingSeconds(500, Number.NaN)).toBeNull()
  })
})

describe('formatDuration', () => {
  it('formats sub-minute durations in seconds', () => {
    expect(formatDuration(0)).toBe('0 s')
    expect(formatDuration(45)).toBe('45 s')
    expect(formatDuration(59.4)).toBe('59 s')
  })

  it('formats minute durations with zero-padded seconds', () => {
    expect(formatDuration(60)).toBe('1 min')
    expect(formatDuration(130)).toBe('2 min 10 s')
    expect(formatDuration(125)).toBe('2 min 05 s')
  })

  it('formats hour durations with zero-padded minutes', () => {
    expect(formatDuration(3600)).toBe('1 h 00 min')
    expect(formatDuration(3900)).toBe('1 h 05 min')
  })
})
