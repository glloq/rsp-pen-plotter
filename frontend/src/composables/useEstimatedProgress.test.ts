import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useEstimatedProgress } from './useEstimatedProgress'

// The composable converts a latency estimate into a determinate-looking
// progress curve: head start → ~80 % at 1× the estimate → asymptote
// below 100 % → snap to 100 % when loading ends. These tests pin the
// curve's invariants rather than exact values, so retuning the
// constants doesn't churn the suite.

describe('useEstimatedProgress', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(0)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  async function setup(estimateMs: number) {
    const loading = ref(false)
    const progress = useEstimatedProgress(
      () => loading.value,
      () => estimateMs,
    )
    return { loading, progress }
  }

  it('starts with a head start and grows monotonically toward the estimate', async () => {
    const { loading, progress } = await setup(1000)
    loading.value = true
    await nextTick()
    const initial = progress.percent.value
    expect(initial).toBeGreaterThan(0)
    expect(initial).toBeLessThan(30)

    vi.advanceTimersByTime(500)
    const half = progress.percent.value
    expect(half).toBeGreaterThan(initial)

    vi.advanceTimersByTime(500)
    const full = progress.percent.value
    expect(full).toBeGreaterThan(half)
    // ~80 % when the estimate elapses.
    expect(full).toBeGreaterThanOrEqual(70)
    expect(full).toBeLessThanOrEqual(85)
  })

  it('never reaches 100 % on its own, even far past the estimate', async () => {
    const { loading, progress } = await setup(200)
    loading.value = true
    await nextTick()
    vi.advanceTimersByTime(10_000)
    expect(progress.percent.value).toBeLessThan(100)
    expect(progress.percent.value).toBeGreaterThanOrEqual(90)
  })

  it('snaps to 100 % when loading ends', async () => {
    const { loading, progress } = await setup(1000)
    loading.value = true
    await nextTick()
    vi.advanceTimersByTime(300)
    loading.value = false
    await nextTick()
    expect(progress.percent.value).toBe(100)
  })

  it('restarts from the head start on the next run', async () => {
    const { loading, progress } = await setup(1000)
    loading.value = true
    await nextTick()
    vi.advanceTimersByTime(800)
    loading.value = false
    await nextTick()
    loading.value = true
    await nextTick()
    expect(progress.percent.value).toBeLessThan(30)
  })

  it('falls back to a generic estimate when the getter returns 0', async () => {
    const { loading, progress } = await setup(0)
    loading.value = true
    await nextTick()
    vi.advanceTimersByTime(400)
    // Still animating (fallback estimate), not frozen at the head start.
    expect(progress.percent.value).toBeGreaterThan(10)
    expect(progress.percent.value).toBeLessThan(100)
  })

  it('starts immediately when created while already loading', async () => {
    const loading = ref(true)
    const progress = useEstimatedProgress(
      () => loading.value,
      () => 500,
    )
    vi.advanceTimersByTime(250)
    expect(progress.percent.value).toBeGreaterThan(10)
  })
})
