import { describe, expect, it } from 'vitest'
import { buildInkLoadingPlan } from './inkPlan'

function layer(id: string, hex: string) {
  return { layerId: id, hex }
}

describe('buildInkLoadingPlan', () => {
  it('loads everything up-front when inks fit the magazine', () => {
    const plan = buildInkLoadingPlan(
      [layer('l1', '#000000'), layer('l2', '#FF0000'), layer('l3', '#00ff00')],
      4,
    )
    expect(plan.inkCount).toBe(3)
    expect(plan.initial).toEqual([
      { slot: 0, hex: '#000000' },
      { slot: 1, hex: '#ff0000' },
      { slot: 2, hex: '#00ff00' },
    ])
    expect(plan.swaps).toEqual([])
    expect(plan.slotByLayer).toEqual({ l1: 0, l2: 1, l3: 2 })
  })

  it('reuses the slot when consecutive layers share an ink', () => {
    const plan = buildInkLoadingPlan(
      [layer('l1', '#000000'), layer('l2', '#000000'), layer('l3', '#ff0000')],
      2,
    )
    expect(plan.initial).toEqual([
      { slot: 0, hex: '#000000' },
      { slot: 1, hex: '#ff0000' },
    ])
    expect(plan.swaps).toEqual([])
    expect(plan.slotByLayer).toEqual({ l1: 0, l2: 0, l3: 1 })
  })

  it('schedules swaps when there are more inks than slots', () => {
    const plan = buildInkLoadingPlan(
      [layer('a', '#111111'), layer('b', '#222222'), layer('c', '#333333'), layer('d', '#444444')],
      2,
    )
    expect(plan.inkCount).toBe(4)
    expect(plan.initial).toHaveLength(2)
    expect(plan.swaps).toEqual([
      { layerId: 'c', slot: 0, hex: '#333333', replacesHex: '#111111' },
      { layerId: 'd', slot: 0, hex: '#444444', replacesHex: '#333333' },
    ])
    expect(plan.slotByLayer).toEqual({ a: 0, b: 1, c: 0, d: 0 })
  })

  it('evicts the ink whose next use is farthest (Belady)', () => {
    // A B C A with 2 slots: at C, A is reused later but B never is —
    // evict B, keep A loaded.
    const plan = buildInkLoadingPlan(
      [layer('a1', '#aa0000'), layer('b', '#00bb00'), layer('c', '#0000cc'), layer('a2', '#aa0000')],
      2,
    )
    expect(plan.swaps).toEqual([{ layerId: 'c', slot: 1, hex: '#0000cc', replacesHex: '#00bb00' }])
    expect(plan.slotByLayer).toEqual({ a1: 0, b: 1, c: 1, a2: 0 })
  })

  it('returns an empty plan without slots or layers', () => {
    expect(buildInkLoadingPlan([], 4).initial).toEqual([])
    expect(buildInkLoadingPlan([layer('l1', '#000000')], 0).initial).toEqual([])
  })

  it('canonicalises hex case so #FF0000 and #ff0000 are one ink', () => {
    const plan = buildInkLoadingPlan([layer('l1', '#FF0000'), layer('l2', '#ff0000')], 2)
    expect(plan.inkCount).toBe(1)
    expect(plan.initial).toEqual([{ slot: 0, hex: '#ff0000' }])
    expect(plan.slotByLayer).toEqual({ l1: 0, l2: 0 })
  })
})
