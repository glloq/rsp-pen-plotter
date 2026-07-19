// @vitest-environment happy-dom
//
// Focused tests for ``useQueueStore`` — covers the skip-layer toast
// priming guard (so historical skipped_layers from a previous session
// don't pop a stale toast at boot) and the single-flight ``load``
// guard. The richer queue UX surfaces (RunTimeline, RunActionsPanel)
// have their own tests; this file owns the store contract.
import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createI18n } from 'vue-i18n'

vi.mock('../api/client', () => ({
  api: {},
  listQueue: vi.fn(),
  enqueuePrint: vi.fn(),
  queueRunAction: vi.fn(),
  deleteQueuedRun: vi.fn(),
}))

// Mock the i18n module so the queue store's
// ``i18n.global.t('queue.skipNotice', ...)`` call resolves against
// our test catalogue. The real ``i18n`` instance has a read-only
// ``global`` accessor, so swapping at runtime is impossible.
vi.mock('../i18n', () => {
  const localI18n = createI18n({
    legacy: false,
    locale: 'fr',
    messages: {
      fr: {
        queue: {
          loadFailed: 'Échec',
          enqueueFailed: 'Échec',
          actionFailed: 'Échec',
          skipNotice: 'Run {name} skipped {layers}.',
        },
      },
    },
  })
  return { i18n: localI18n }
})

import { listQueue, type PrintRun } from '../api/client'
import { useQueueStore } from './queue'
import { useToastStore } from './toasts'

function makeRun(over: Partial<PrintRun> = {}): PrintRun {
  return {
    id: over.id ?? 'run-1',
    name: over.name ?? 'job',
    profile_name: 'p',
    gcode: '',
    total_lines: 10,
    acked_lines: 0,
    state: 'queued',
    priority: 0,
    error: null,
    skipped_layers: over.skipped_layers ?? [],
    created_at: '2026-05-28T00:00:00Z',
    updated_at: '2026-05-28T00:00:00Z',
    ...over,
  }
}

describe('useQueueStore — skip_layer toast priming', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(listQueue).mockReset()
  })

  it('does NOT emit a critical toast on the first load for pre-existing skips', async () => {
    vi.mocked(listQueue).mockResolvedValueOnce([makeRun({ skipped_layers: ['A', 'B'] })])
    const queue = useQueueStore()
    const toasts = useToastStore()
    await queue.load()
    expect(toasts.toasts.filter((t) => t.kind === 'error')).toHaveLength(0)
  })

  it('emits a critical toast on a subsequent load when skips grow', async () => {
    vi.mocked(listQueue)
      .mockResolvedValueOnce([makeRun({ skipped_layers: ['A'] })])
      .mockResolvedValueOnce([makeRun({ skipped_layers: ['A', 'B'] })])
    const queue = useQueueStore()
    const toasts = useToastStore()
    await queue.load() // priming, no toast
    expect(toasts.toasts).toHaveLength(0)
    await queue.load() // delta detected → critical
    const criticals = toasts.toasts.filter((t) => t.kind === 'error' && t.persistent)
    expect(criticals).toHaveLength(1)
    expect(criticals[0]?.message).toContain('B')
  })

  it('does not double-fire when the same delta is reported in successive polls', async () => {
    vi.mocked(listQueue)
      .mockResolvedValueOnce([makeRun({ skipped_layers: [] })])
      .mockResolvedValueOnce([makeRun({ skipped_layers: ['X'] })])
      .mockResolvedValueOnce([makeRun({ skipped_layers: ['X'] })])
    const queue = useQueueStore()
    const toasts = useToastStore()
    await queue.load()
    await queue.load()
    await queue.load()
    const criticals = toasts.toasts.filter((t) => t.persistent)
    expect(criticals).toHaveLength(1)
  })
})

describe('useQueueStore — single-flight load', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(listQueue).mockReset()
  })

  it('coalesces concurrent load() calls into one network request', async () => {
    let resolve: ((value: PrintRun[]) => void) | null = null
    const pending = new Promise<PrintRun[]>((r) => {
      resolve = r
    })
    vi.mocked(listQueue).mockReturnValue(pending)
    const queue = useQueueStore()
    const p1 = queue.load()
    const p2 = queue.load()
    expect(vi.mocked(listQueue)).toHaveBeenCalledTimes(1)
    resolve!([])
    await Promise.all([p1, p2])
  })
})

describe('useQueueStore — /ws/queue push frames', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(listQueue).mockReset()
  })

  it('applies a push frame like a poll: runs update + skip toast fires', async () => {
    vi.mocked(listQueue).mockResolvedValueOnce([makeRun({ skipped_layers: [] })])
    const queue = useQueueStore()
    const toasts = useToastStore()
    await queue.load() // primes the skip bookkeeping
    // A WS frame reporting a new skip must fire the critical toast the
    // same way a poll does (shared applyRuns path).
    queue.applyRuns([makeRun({ skipped_layers: ['Bleu'] })])
    expect(queue.runs).toHaveLength(1)
    expect(queue.runs[0]?.skipped_layers).toEqual(['Bleu'])
    expect(toasts.toasts.some((t) => t.message.includes('Bleu'))).toBe(true)
  })
})
