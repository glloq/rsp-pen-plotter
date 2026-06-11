import { describe, expect, it } from 'vitest'

import {
  KNOB_UNITS_MM,
  PX_TO_MM,
  convertLegacyStyleKnobs,
  isLegacyKnobPayload,
} from './legacyKnobUnits'

describe('legacyKnobUnits', () => {
  it('detects px-era payloads by the missing knob_units marker', () => {
    expect(isLegacyKnobPayload({})).toBe(true)
    expect(isLegacyKnobPayload({ knob_units: 'px' })).toBe(true)
    expect(isLegacyKnobPayload({ knob_units: KNOB_UNITS_MM })).toBe(false)
  })

  it('rescales suffix-less length fields and renames _px twins', () => {
    const out = convertLegacyStyleKnobs({
      spacing_min: 2.5,
      spacing_max: 6.5,
      wave_period: 14,
      step_px: 0.8,
      wave_amp_px: 2,
    })
    expect(out.spacing_min).toBeCloseTo(2.5 * PX_TO_MM, 2)
    expect(out.spacing_max).toBeCloseTo(6.5 * PX_TO_MM, 2)
    expect(out.wave_period).toBeCloseTo(14 * PX_TO_MM, 2)
    expect(out.step_px).toBeUndefined()
    expect(out.step_mm).toBeCloseTo(0.8 * PX_TO_MM, 2)
    expect(out.wave_amp_mm).toBeCloseTo(2 * PX_TO_MM, 2)
  })

  it('passes dimensionless fields and unknown keys through untouched', () => {
    const angles = [45, 135]
    const perBand = { 0: { spacing_mm: 1 } }
    const out = convertLegacyStyleKnobs({
      density_min: 0.02,
      rings_max: 40,
      angle_step: 45,
      crossed: true,
      angles,
      perBand,
      algoOverrides: { foo: 1 },
    })
    expect(out.density_min).toBe(0.02)
    expect(out.rings_max).toBe(40)
    expect(out.angle_step).toBe(45)
    expect(out.crossed).toBe(true)
    expect(out.angles).toBe(angles)
    expect(out.perBand).toBe(perBand)
    expect(out.algoOverrides).toEqual({ foo: 1 })
  })
})
