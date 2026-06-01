import { describe, expect, it } from 'vitest'
import type { MachineProfile } from '../api/client'
import { computePlacement, unionBounds } from './placement'

function profile(overrides: Partial<MachineProfile> = {}): MachineProfile {
  return {
    name: 'Test',
    units: 'mm',
    workspace: { x_min: 0, y_min: 0, x_max: 420, y_max: 297 },
    origin: 'top_left',
    gcode_dialect: 'grbl',
    pen_up_command: '',
    pen_down_command: '',
    tool_change_method: 'manual_pause',
    tool_change_command: '',
    drawing_speed_mm_s: 60,
    travel_speed_mm_s: 120,
    acceleration_mm_s2: 1000,
    pen_lift_time_ms: 0,
    pen_slot_count: 1,
    supports_arcs: false,
    arc_tolerance_mm: 0.1,
    ebb: null,
    pens: null,
    ...overrides,
  }
}

describe('unionBounds', () => {
  it('returns null for no boxes', () => {
    expect(unionBounds([])).toBeNull()
  })

  it('merges several boxes into their envelope', () => {
    const u = unionBounds([
      { x_min: 0, y_min: 0, x_max: 10, y_max: 5 },
      { x_min: 4, y_min: -2, x_max: 20, y_max: 8 },
    ])
    expect(u).toEqual({ x_min: 0, y_min: -2, x_max: 20, y_max: 8 })
  })
})

describe('computePlacement', () => {
  const bounds = { x_min: 0, y_min: 0, x_max: 100, y_max: 50 }

  it('fits to the sheet honouring the margin', () => {
    const p = computePlacement(bounds, profile(), 'fit', 10)
    // usable 400x277 over 100x50 -> limited by width: 400/100 = 4
    expect(p.scale).toBeCloseTo(4, 6)
    expect(p.widthMm).toBeCloseTo(400, 6)
    expect(p.heightMm).toBeCloseTo(200, 6)
    expect(p.exceeds).toBe(false)
    // centered on the sheet centre (210, 148.5)
    expect(p.footprint.x_min).toBeCloseTo(10, 6)
    expect(p.footprint.x_max).toBeCloseTo(410, 6)
    expect(p.footprint.y_min).toBeCloseTo(48.5, 6)
    expect(p.footprint.y_max).toBeCloseTo(248.5, 6)
  })

  it('keeps actual size at scale 1', () => {
    const p = computePlacement(bounds, profile(), 'actual', 10)
    expect(p.scale).toBe(1)
    expect(p.widthMm).toBeCloseTo(100, 6)
    expect(p.heightMm).toBeCloseTo(50, 6)
    expect(p.exceeds).toBe(false)
  })

  it('flags drawings that overflow the workspace', () => {
    const big = { x_min: 0, y_min: 0, x_max: 1000, y_max: 1000 }
    const p = computePlacement(big, profile(), 'actual', 10)
    expect(p.exceeds).toBe(true)
  })
})
