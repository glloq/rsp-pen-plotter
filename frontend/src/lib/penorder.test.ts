import { describe, expect, it } from 'vitest'
import type { LayerInfo } from '../api/client'
import { canReduceSwaps, countPenChanges, groupByPen } from './penorder'

function layer(id: string, slot: number | null): LayerInfo {
  return {
    layer_id: id,
    source_color: '#000',
    target_pen_slot: slot,
    draw_order: 0,
    total_length_mm: 1,
    path_count: 1,
    bbox: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 },
    optimize: true,
    simplify_tolerance_mm: 0.05,
    drawing_speed_mm_s: null,
    color_label: null,
    pause_before: 'auto',
    assigned_color_hex: null,
    color_assignment: 'auto',
  }
}

describe('countPenChanges', () => {
  it('counts transitions between assigned slots', () => {
    // 0, 1, 0 -> three changes (each entry switches slot)
    expect(countPenChanges([layer('a', 0), layer('b', 1), layer('c', 0)])).toBe(3)
  })

  it('ignores unassigned layers', () => {
    expect(countPenChanges([layer('a', 0), layer('b', null), layer('c', 0)])).toBe(1)
  })
})

describe('groupByPen', () => {
  it('groups layers by slot in first-appearance order, stable within a group', () => {
    const input = [layer('a', 0), layer('b', 1), layer('c', 0), layer('d', 1)]
    const ids = groupByPen(input).map((l) => l.layer_id)
    expect(ids).toEqual(['a', 'c', 'b', 'd'])
  })

  it('reduces the swap count', () => {
    const input = [layer('a', 0), layer('b', 1), layer('c', 0), layer('d', 1)]
    expect(countPenChanges(input)).toBe(4)
    expect(countPenChanges(groupByPen(input))).toBe(2)
  })
})

describe('canReduceSwaps', () => {
  it('is true when interleaved, false when already grouped', () => {
    expect(canReduceSwaps([layer('a', 0), layer('b', 1), layer('c', 0)])).toBe(true)
    expect(canReduceSwaps([layer('a', 0), layer('b', 0), layer('c', 1)])).toBe(false)
  })
})
