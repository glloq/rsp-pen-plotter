import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

import { useEditorPreviewStream } from './useEditorPreviewStream'
import type { StreamHandle, ProgressEvent } from './useProgressiveStream'
import type { EstimatedProgress } from './useEstimatedProgress'

// Minimal stub stream handle: real refs the test can drive, plus open/close
// spies so we can assert the open/close lifecycle without a real EventSource.
function makeStreamStub() {
  const lastProgress = ref<ProgressEvent | null>(null)
  const percent = ref(0)
  const active = ref(false)
  const open = vi.fn((_url: string) => {
    active.value = true
  })
  const close = vi.fn(() => {
    active.value = false
  })
  const stub = {
    start: ref(null),
    lastProgress,
    lastPartial: ref(null),
    done: ref(null),
    error: ref(null),
    active,
    percent,
    open,
    close,
  } as unknown as StreamHandle
  return { stub, lastProgress, percent, active, open, close }
}

function makeEstimatedStub(): { stub: EstimatedProgress; percent: ReturnType<typeof ref<number>> } {
  const percent = ref(0)
  return { stub: { percent } as EstimatedProgress, percent }
}

describe('useEditorPreviewStream', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('does not open the stream for previews that resolve under 350 ms', async () => {
    const loading = ref(false)
    const stream = makeStreamStub()
    const estimated = makeEstimatedStub()
    useEditorPreviewStream(
      { loading: () => loading.value, streamFileId: () => 'file-1', estimateMs: () => 800 },
      { stream: stream.stub, estimatedProgress: estimated.stub },
    )
    loading.value = true
    await nextTick()
    // The render finishes before the open timer fires…
    vi.advanceTimersByTime(300)
    loading.value = false
    await nextTick()
    vi.advanceTimersByTime(100)
    expect(stream.open).not.toHaveBeenCalled()
  })

  it('opens the stream once the slow-preview delay elapses', async () => {
    const loading = ref(false)
    const stream = makeStreamStub()
    const estimated = makeEstimatedStub()
    useEditorPreviewStream(
      { loading: () => loading.value, streamFileId: () => 'file-1', estimateMs: () => 800 },
      { stream: stream.stub, estimatedProgress: estimated.stub },
    )
    loading.value = true
    await nextTick()
    vi.advanceTimersByTime(350)
    expect(stream.open).toHaveBeenCalledWith('/preview/stream?file_id=file-1')
  })

  it('closes the stream when loading flips off', async () => {
    const loading = ref(false)
    const stream = makeStreamStub()
    const estimated = makeEstimatedStub()
    useEditorPreviewStream(
      { loading: () => loading.value, streamFileId: () => 'file-1', estimateMs: () => 800 },
      { stream: stream.stub, estimatedProgress: estimated.stub },
    )
    loading.value = true
    await nextTick()
    vi.advanceTimersByTime(350)
    loading.value = false
    await nextTick()
    expect(stream.close).toHaveBeenCalled()
  })

  it('never opens the stream without a file id to stream from', async () => {
    const loading = ref(false)
    const stream = makeStreamStub()
    const estimated = makeEstimatedStub()
    useEditorPreviewStream(
      { loading: () => loading.value, streamFileId: () => null, estimateMs: () => 800 },
      { stream: stream.stub, estimatedProgress: estimated.stub },
    )
    loading.value = true
    await nextTick()
    vi.advanceTimersByTime(1000)
    expect(stream.open).not.toHaveBeenCalled()
  })

  it('does not open if the file id changed during the delay window', async () => {
    const loading = ref(false)
    const fileId = ref<string | null>('file-1')
    const stream = makeStreamStub()
    const estimated = makeEstimatedStub()
    useEditorPreviewStream(
      { loading: () => loading.value, streamFileId: () => fileId.value, estimateMs: () => 800 },
      { stream: stream.stub, estimatedProgress: estimated.stub },
    )
    loading.value = true
    await nextTick()
    fileId.value = 'file-2' // placement swapped mid-delay
    vi.advanceTimersByTime(350)
    expect(stream.open).not.toHaveBeenCalled()
  })

  it('shows whichever of stream vs. estimated percent is further along', () => {
    const stream = makeStreamStub()
    const estimated = makeEstimatedStub()
    const { displayPercent } = useEditorPreviewStream(
      { loading: () => true, streamFileId: () => 'file-1', estimateMs: () => 800 },
      { stream: stream.stub, estimatedProgress: estimated.stub },
    )
    // Stream inactive → estimated carries it alone.
    estimated.percent.value = 42
    expect(displayPercent.value).toBe(42)
    // Stream active and ahead → stream wins.
    stream.active.value = true
    stream.percent.value = 70
    expect(displayPercent.value).toBe(70)
    // Estimated overtakes the stream → estimated wins (bar only moves forward).
    estimated.percent.value = 85
    expect(displayPercent.value).toBe(85)
  })

  it('surfaces the last layer label from the stream payload', () => {
    const stream = makeStreamStub()
    const estimated = makeEstimatedStub()
    const { streamLabel, streamActive } = useEditorPreviewStream(
      { loading: () => true, streamFileId: () => 'file-1', estimateMs: () => 800 },
      { stream: stream.stub, estimatedProgress: estimated.stub },
    )
    expect(streamLabel.value).toBe('')
    expect(streamActive.value).toBe(false)
    stream.lastProgress.value = {
      kind: 'progress',
      sequence: 1,
      elapsed_ms: 10,
      payload: { layer_label: 'Cyan' },
    }
    stream.active.value = true
    expect(streamLabel.value).toBe('Cyan')
    expect(streamActive.value).toBe(true)
  })
})
