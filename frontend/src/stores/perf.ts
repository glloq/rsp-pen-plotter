// Frontend perf tracking store (roadmap C.8).
//
// Collects KPI samples in-memory and exposes them to the perf
// overlay. The overlay is activated via the C.1 feature-flag store
// (`flag.perf=1` URL override or persisted toggle). No samples are
// dropped on the floor when the overlay is off — the cost of pushing
// to a ring buffer is negligible — but they're also never reported
// anywhere by default; the overlay is the only consumer until the
// SLO budgets land in D.4.

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export type PerfKpi =
  | 'time_to_first_preview'
  | 'preview_refresh'
  | 'slow_interaction'
  | 'frame_drop'
  | 'network_error'

export interface PerfSample {
  kpi: PerfKpi
  /** Wall-clock when the sample was recorded (ms since epoch). */
  recorded_at: number
  /** Sample value (ms for timings, 1 for events). */
  value: number
  /** Optional label (algorithm name, route, …) for the dashboard. */
  label?: string
}

const RING_SIZE = 200

export const usePerfStore = defineStore('perf', () => {
  const samples = ref<PerfSample[]>([])
  const errors = ref<number>(0)

  function record(sample: PerfSample): void {
    samples.value.push(sample)
    if (samples.value.length > RING_SIZE) samples.value.shift()
    if (sample.kpi === 'network_error') errors.value += 1
  }

  function recordTiming(kpi: PerfKpi, ms: number, label?: string): void {
    record({ kpi, value: ms, recorded_at: Date.now(), label })
  }

  function clear(): void {
    samples.value = []
    errors.value = 0
  }

  const byKpi = computed<Map<PerfKpi, PerfSample[]>>(() => {
    const out = new Map<PerfKpi, PerfSample[]>()
    for (const s of samples.value) {
      const list = out.get(s.kpi) ?? []
      list.push(s)
      out.set(s.kpi, list)
    }
    return out
  })

  function summary(kpi: PerfKpi): {
    count: number
    p50: number
    p95: number
    last: number
  } {
    const list = byKpi.value.get(kpi) ?? []
    if (list.length === 0) return { count: 0, p50: 0, p95: 0, last: 0 }
    const values = list.map((s) => s.value).sort((a, b) => a - b)
    const idx = (p: number): number =>
      Math.max(0, Math.min(values.length - 1, Math.round((p / 100) * (values.length - 1))))
    return {
      count: values.length,
      p50: values[idx(50)] ?? 0,
      p95: values[idx(95)] ?? 0,
      last: list[list.length - 1]?.value ?? 0,
    }
  }

  return { samples, errors, record, recordTiming, clear, byKpi, summary }
})
