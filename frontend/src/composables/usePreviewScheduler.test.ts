// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const previewBitmap = vi.fn()
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return {
    ...actual,
    previewBitmap: (...args: unknown[]) => previewBitmap(...args),
  }
})

import { usePreviewScheduler } from './usePreviewScheduler'
import { useToastStore } from '../stores/toasts'

function makeScheduler() {
  return usePreviewScheduler({
    fileGetter: () => new File(['x'], 'x.png', { type: 'image/png' }),
    algorithmGetter: () => 'crosshatch',
    optionsBuilder: () => ({}),
    shouldRun: () => true,
    toastDelayMs: 100,
  })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

const RESULT = { svg: '<svg/>', elapsed_ms: 5, palette: [], warnings: [], cached: false }

describe('usePreviewScheduler toast lifecycle', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    previewBitmap.mockReset()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("a superseded run does not dismiss the newer run's toast", async () => {
    const toasts = useToastStore()
    const scheduler = makeScheduler()

    // Run A: never-resolving until we say so.
    const a = deferred<typeof RESULT>()
    previewBitmap.mockReturnValueOnce(a.promise)
    scheduler.schedule({ immediate: true })

    // Run B supersedes A before A settles.
    const b = deferred<typeof RESULT>()
    previewBitmap.mockReturnValueOnce(b.promise)
    scheduler.schedule({ immediate: true })

    // B's toast appears after the delay.
    await vi.advanceTimersByTimeAsync(150)
    expect(toasts.toasts.some((t) => t.kind === 'progress')).toBe(true)

    // A settles late (it was aborted/superseded) — its finally must NOT
    // kill B's toast.
    a.resolve(RESULT)
    await vi.advanceTimersByTimeAsync(0)
    expect(toasts.toasts.some((t) => t.kind === 'progress')).toBe(true)

    // B settles → its own toast goes away.
    b.resolve(RESULT)
    await vi.advanceTimersByTimeAsync(0)
    expect(toasts.toasts.some((t) => t.kind === 'progress')).toBe(false)
    expect(scheduler.previewResult.value).toEqual(RESULT)
  })

  it('dismisses the toast when the (only) run finishes', async () => {
    const toasts = useToastStore()
    const scheduler = makeScheduler()
    const a = deferred<typeof RESULT>()
    previewBitmap.mockReturnValueOnce(a.promise)
    scheduler.schedule({ immediate: true })
    await vi.advanceTimersByTimeAsync(150)
    expect(toasts.toasts.some((t) => t.kind === 'progress')).toBe(true)
    a.resolve(RESULT)
    await vi.advanceTimersByTimeAsync(0)
    expect(toasts.toasts.some((t) => t.kind === 'progress')).toBe(false)
  })
})
