import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { beginProgressToast } from './progressToast'
import { useToastStore } from '../stores/toasts'

// The helper drives the real toast store; we assert on its public
// ``toasts`` list rather than mocking it, so the test also guards the
// store wiring (progress field, setProgress, update).

describe('beginProgressToast', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.setSystemTime(0)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows a progress toast immediately with a determinate bar when an estimate is given', () => {
    const store = useToastStore()
    const handle = beginProgressToast({ message: 'Rendering', estimateMs: 10_000 })
    expect(store.toasts).toHaveLength(1)
    const toast = store.toasts[0]!
    expect(toast.kind).toBe('progress')
    expect(toast.message.startsWith('Rendering')).toBe(true)
    // ETA suffix appended (message longer than the base line).
    expect(toast.message.length).toBeGreaterThan('Rendering'.length)
    expect(typeof toast.progress).toBe('number')
    expect(toast.progress).toBeGreaterThanOrEqual(0)
    expect(toast.progress).toBeLessThan(100)
    handle.dismiss()
  })

  it('advances the bar and refreshes the remaining-time message over time', () => {
    const store = useToastStore()
    const handle = beginProgressToast({ message: 'Rendering', estimateMs: 10_000 })
    const initial = store.toasts[0]!.progress as number
    vi.advanceTimersByTime(5_000)
    const later = store.toasts[0]!.progress as number
    expect(later).toBeGreaterThan(initial)
    handle.dismiss()
  })

  it('omits the bar (indeterminate) when no estimate is supplied', () => {
    const store = useToastStore()
    const handle = beginProgressToast({ message: 'Working' })
    expect(store.toasts[0]!.message).toBe('Working')
    expect(store.toasts[0]!.progress).toBeUndefined()
    handle.dismiss()
  })

  it('defers the toast and never shows it when the op finishes before showAfterMs', () => {
    const store = useToastStore()
    const handle = beginProgressToast({ message: 'Rendering', showAfterMs: 400 })
    expect(store.toasts).toHaveLength(0)
    vi.advanceTimersByTime(300)
    expect(store.toasts).toHaveLength(0)
    // Fast success before the show timer fires → stays silent.
    handle.succeed('done')
    vi.advanceTimersByTime(500)
    expect(store.toasts).toHaveLength(0)
  })

  it('shows the deferred toast once showAfterMs elapses', () => {
    const store = useToastStore()
    const handle = beginProgressToast({ message: 'Rendering', showAfterMs: 400 })
    vi.advanceTimersByTime(400)
    expect(store.toasts).toHaveLength(1)
    expect(store.toasts[0]!.kind).toBe('progress')
    handle.dismiss()
  })

  it('switches to real progress on setProgress — labelled, monotonic, no backward jump', () => {
    const store = useToastStore()
    const handle = beginProgressToast({ message: 'Rendering', estimateMs: 10_000 })
    vi.advanceTimersByTime(2_000)
    const estimatePct = store.toasts[0]!.progress as number
    expect(estimatePct).toBeGreaterThan(0)
    // A real tick at a LOWER raw percent than the estimate must not yank
    // the bar backwards (it's seeded from the estimate) and switches the
    // message from the ETA to the layer label.
    handle.setProgress(5, 'Layer 1/4')
    const afterFirst = store.toasts[0]!
    expect(afterFirst.progress).toBeGreaterThanOrEqual(estimatePct)
    expect(afterFirst.message).toContain('Layer 1/4')
    expect(afterFirst.message).not.toContain('remaining')
    // A higher real tick advances the bar and updates the label.
    handle.setProgress(60, 'Layer 3/4')
    expect(store.toasts[0]!.progress).toBeGreaterThanOrEqual(60)
    expect(store.toasts[0]!.message).toContain('Layer 3/4')
    handle.dismiss()
  })

  it('transforms a shown toast into a success toast on succeed()', () => {
    const store = useToastStore()
    const handle = beginProgressToast({ message: 'Rendering' })
    const id = store.toasts[0]!.id
    handle.succeed('Done')
    expect(store.toasts).toHaveLength(1)
    expect(store.toasts[0]!.id).toBe(id)
    expect(store.toasts[0]!.kind).toBe('success')
    expect(store.toasts[0]!.message).toBe('Done')
  })

  it('surfaces an error toast on fail() even when the toast was never shown', () => {
    const store = useToastStore()
    const handle = beginProgressToast({ message: 'Rendering', showAfterMs: 400 })
    expect(store.toasts).toHaveLength(0)
    handle.fail('Boom')
    expect(store.toasts).toHaveLength(1)
    expect(store.toasts[0]!.kind).toBe('error')
    expect(store.toasts[0]!.message).toBe('Boom')
  })

  it('wires a cancel action that invokes the abort hook', () => {
    const store = useToastStore()
    const cancel = vi.fn()
    const handle = beginProgressToast({ message: 'Rendering', cancel })
    const action = store.toasts[0]!.action
    expect(action).toBeTruthy()
    action!.onClick()
    expect(cancel).toHaveBeenCalledOnce()
    handle.dismiss()
  })

  it('is idempotent across terminal calls and stops ticking after settle', () => {
    const store = useToastStore()
    const handle = beginProgressToast({ message: 'Rendering', estimateMs: 10_000 })
    handle.succeed('Done')
    // Subsequent terminal calls are no-ops (settled guard) — no extra
    // toast spawned, message stays at the success line.
    handle.fail('Boom')
    handle.dismiss()
    expect(store.toasts).toHaveLength(1)
    expect(store.toasts[0]!.kind).toBe('success')
    expect(store.toasts[0]!.message).toBe('Done')
    // Ticker stopped — advancing time (within the success ttl) doesn't
    // mutate the settled toast back into a progress readout.
    vi.advanceTimersByTime(1_000)
    expect(store.toasts[0]!.message).toBe('Done')
    expect(store.toasts[0]!.kind).toBe('success')
  })
})
