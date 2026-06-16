// Estimated determinate progress for single-round-trip computations.
//
// /preview is one synchronous request — the backend can't report
// fine-grained progress for it (the SSE stream only ticks once per
// rendered *layer*, useless for the common single-band mono case).
// What we do have is a good per-(algorithm × quality) latency estimate
// from ``usePreviewCostEstimator``'s EMA. This composable turns that
// estimate into a smooth determinate-looking bar:
//
//   - jumps to a small head start immediately (perceived response),
//   - fills linearly to ~80 % at 1× the estimate,
//   - then decays asymptotically toward ~98 % — never reaching 100 %
//     on its own, so a longer-than-estimated render still shows
//     forward motion instead of a stuck-full bar,
//   - snaps to 100 % the moment loading flips off (the overlay is
//     hidden right after, so the snap reads as completion).
//
// The estimate is sampled once per run (at loading-start) so a
// mid-flight EMA update can't make the bar jump backwards.

import { onScopeDispose, ref, watch, type Ref } from 'vue'
import { estimatedPercent } from '../lib/progressEstimate'

const TICK_MS = 120
// Fallback when the caller can't produce an estimate (no algorithm
// selected yet) — roughly a Standard-tier medium algorithm.
const FALLBACK_ESTIMATE_MS = 800

export interface EstimatedProgress {
  /** 0..100, animated while ``loading`` is true. */
  percent: Ref<number>
}

export function useEstimatedProgress(
  isLoading: () => boolean,
  estimateMsGetter: () => number,
): EstimatedProgress {
  const percent = ref(0)
  let timer: ReturnType<typeof setInterval> | null = null
  let startedAt = 0
  let estimate = FALLBACK_ESTIMATE_MS

  function stopTimer(): void {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  function tick(): void {
    percent.value = estimatedPercent(Date.now() - startedAt, estimate)
  }

  function start(): void {
    stopTimer()
    startedAt = Date.now()
    const raw = estimateMsGetter()
    estimate = Number.isFinite(raw) && raw > 0 ? raw : FALLBACK_ESTIMATE_MS
    percent.value = estimatedPercent(0, estimate)
    timer = setInterval(tick, TICK_MS)
  }

  function finish(): void {
    stopTimer()
    // Snap to full — the consumer hides the bar when loading ends, so
    // the brief 100 % reads as the completion beat.
    if (percent.value > 0) percent.value = 100
  }

  watch(isLoading, (loading) => {
    if (loading) start()
    else finish()
  })

  // The component may mount with a render already in flight (the modal
  // opens while the first preview runs) — start immediately in that case.
  if (isLoading()) start()

  onScopeDispose(stopTimer)

  return { percent }
}
