// Preview cost estimator.
//
// Builds an exponentially-weighted moving average of /preview latency
// per (algorithm, quality) pair from the ``elapsed_ms`` reported by the
// backend's ``PreviewResponse``. The preview pane uses this to surface
// a cost chip *before* the next round-trip — so the operator sees
// "~1.4s" when they hover the Final tier on a TSP layer instead of
// finding out the hard way.
//
// Why an EMA rather than a fixed cost table:
//   - Real /preview cost depends on image size + segmentation depth +
//     hardware. The static ``AlgorithmInfo.complexity`` from the
//     backend only gives the order of magnitude; the EMA fixes the
//     constant once we've observed the actual device.
//   - Cache hits skew downward and aren't useful as cost samples;
//     ``cached`` responses are filtered out before the EMA update.
//
// State is persisted to localStorage so the estimator survives reloads.
// The EMA factor (0.3) trades latency-of-correction (fast adapt to a
// new image's cost profile) for stability (single jitter doesn't yank
// the displayed estimate). Picked by eye, not tuned.

import { computed, type ComputedRef, ref } from 'vue'
import type { AlgorithmComplexity, PreviewQuality } from '../api/client'

const STORAGE_KEY = 'previewCostSamples.v1'
const EMA_ALPHA = 0.3
// First-observation gate: ignore samples shorter than this. Below it,
// the response was likely a cache near-hit or a cold-start outlier
// (e.g. lazy import) rather than the algorithm's real cost.
const MIN_SAMPLE_MS = 20

// Quality tier multipliers applied to the seed estimate. Standard
// matches the historical /preview behaviour and is the 1.0 baseline;
// Draft caps resolution at 256 px so it's noticeably faster; Final
// pays for 10 k-means restarts so it's noticeably slower.
const QUALITY_FACTORS: Record<PreviewQuality, number> = {
  draft: 0.45,
  standard: 1.0,
  final: 3.5,
}

// Seed estimates per complexity bucket, in milliseconds at the Standard
// tier on a Pi-class device. Rough — the EMA replaces them after the
// first real observation.
const COMPLEXITY_SEEDS: Record<AlgorithmComplexity, number> = {
  low: 120,
  medium: 400,
  high: 1500,
}

type Samples = Record<string, number>

function _key(algorithm: string, quality: PreviewQuality): string {
  return `${algorithm}::${quality}`
}

function _load(): Samples {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object') return parsed as Samples
  } catch {
    /* corrupt or unavailable — start fresh */
  }
  return {}
}

function _save(samples: Samples): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(samples))
  } catch {
    /* ignore */
  }
}

// Module-level singleton so every consumer reads the same EMA. The
// preview pane and any future estimate-aware UI share a single store.
const _samples = ref<Samples>(_load())

export interface PreviewCostEstimator {
  // Returns the best current estimate in ms for the given algorithm +
  // quality. Falls back to the complexity seed × quality factor when
  // no real sample has been observed yet. Always returns a positive
  // number so the UI can render unconditionally.
  estimateMs: (
    algorithm: string,
    quality: PreviewQuality,
    complexity?: AlgorithmComplexity,
  ) => number
  // Record an observed /preview latency. Cache hits should be filtered
  // out by the caller (they aren't representative of compute cost).
  record: (algorithm: string, quality: PreviewQuality, elapsedMs: number) => void
  // Reactive view used by component templates that want to refresh when
  // a new sample lands.
  samples: ComputedRef<Samples>
}

export function usePreviewCostEstimator(): PreviewCostEstimator {
  function estimateMs(
    algorithm: string,
    quality: PreviewQuality,
    complexity: AlgorithmComplexity = 'medium',
  ): number {
    const observed = _samples.value[_key(algorithm, quality)]
    if (typeof observed === 'number' && observed > 0) return observed
    // No direct observation yet — try the Standard slot for the same
    // algorithm, then scale by the tier factor. Lets a single warmed-up
    // Standard sample seed the Draft and Final chips immediately.
    const standardObs = _samples.value[_key(algorithm, 'standard')]
    if (typeof standardObs === 'number' && standardObs > 0) {
      return standardObs * QUALITY_FACTORS[quality]
    }
    return COMPLEXITY_SEEDS[complexity] * QUALITY_FACTORS[quality]
  }

  function record(algorithm: string, quality: PreviewQuality, elapsedMs: number): void {
    if (!Number.isFinite(elapsedMs) || elapsedMs < MIN_SAMPLE_MS) return
    const key = _key(algorithm, quality)
    const prev = _samples.value[key]
    const next =
      typeof prev === 'number' && prev > 0
        ? prev * (1 - EMA_ALPHA) + elapsedMs * EMA_ALPHA
        : elapsedMs
    _samples.value = { ..._samples.value, [key]: Math.round(next) }
    _save(_samples.value)
  }

  return {
    estimateMs,
    record,
    samples: computed(() => _samples.value),
  }
}
