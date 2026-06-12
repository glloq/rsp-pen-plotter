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

function makeScheduler() {
  return usePreviewScheduler({
    fileGetter: () => new File(['x'], 'x.png', { type: 'image/png' }),
    algorithmGetter: () => 'crosshatch',
    optionsBuilder: () => ({}),
    shouldRun: () => true,
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

describe('usePreviewScheduler loading lifecycle', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    previewBitmap.mockReset()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("a superseded run does not clear the newer run's loading flag", async () => {
    const scheduler = makeScheduler()

    // Run A: never-resolving until we say so.
    const a = deferred<typeof RESULT>()
    previewBitmap.mockReturnValueOnce(a.promise)
    scheduler.schedule({ immediate: true })

    // Run B supersedes A before A settles.
    const b = deferred<typeof RESULT>()
    previewBitmap.mockReturnValueOnce(b.promise)
    scheduler.schedule({ immediate: true })
    expect(scheduler.previewLoading.value).toBe(true)

    // A settles late (it was aborted/superseded) — its finally must NOT
    // clear B's loading flag.
    a.resolve(RESULT)
    await vi.advanceTimersByTimeAsync(0)
    expect(scheduler.previewLoading.value).toBe(true)

    // B settles → loading clears and B's result wins.
    b.resolve(RESULT)
    await vi.advanceTimersByTimeAsync(0)
    expect(scheduler.previewLoading.value).toBe(false)
    expect(scheduler.previewResult.value).toEqual(RESULT)
  })

  it('clears the loading flag when the (only) run finishes', async () => {
    const scheduler = makeScheduler()
    const a = deferred<typeof RESULT>()
    previewBitmap.mockReturnValueOnce(a.promise)
    scheduler.schedule({ immediate: true })
    expect(scheduler.previewLoading.value).toBe(true)
    a.resolve(RESULT)
    await vi.advanceTimersByTimeAsync(0)
    expect(scheduler.previewLoading.value).toBe(false)
  })
})
