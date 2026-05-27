// Tiny helper around the perf store (roadmap C.8).
//
// Two flavours:
//   - `time(kpi, label?, fn)`        — sync; returns whatever fn returns.
//   - `timeAsync(kpi, label?, fn)`   — same but awaits fn.
// Both push one sample on completion. Slow interactions (>100 ms) also
// emit a `slow_interaction` sample so the overlay can highlight them.

import { usePerfStore, type PerfKpi } from '../stores/perf'

const SLOW_INTERACTION_MS = 100

export function usePerfTracker(): {
  time: <T>(kpi: PerfKpi, label: string | undefined, fn: () => T) => T
  timeAsync: <T>(kpi: PerfKpi, label: string | undefined, fn: () => Promise<T>) => Promise<T>
  recordError: (label?: string) => void
} {
  const store = usePerfStore()

  function flag(elapsed: number, label?: string): void {
    if (elapsed > SLOW_INTERACTION_MS) {
      store.recordTiming('slow_interaction', elapsed, label)
    }
  }

  function time<T>(kpi: PerfKpi, label: string | undefined, fn: () => T): T {
    const start = performance.now()
    try {
      return fn()
    } finally {
      const elapsed = performance.now() - start
      store.recordTiming(kpi, elapsed, label)
      flag(elapsed, label)
    }
  }

  async function timeAsync<T>(
    kpi: PerfKpi,
    label: string | undefined,
    fn: () => Promise<T>,
  ): Promise<T> {
    const start = performance.now()
    try {
      return await fn()
    } finally {
      const elapsed = performance.now() - start
      store.recordTiming(kpi, elapsed, label)
      flag(elapsed, label)
    }
  }

  function recordError(label?: string): void {
    store.record({
      kpi: 'network_error',
      value: 1,
      recorded_at: Date.now(),
      label,
    })
  }

  return { time, timeAsync, recordError }
}
