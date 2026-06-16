// Shared math for determinate-looking progress from a duration estimate.
//
// Extracted so the preview-overlay bar (``useEstimatedProgress``) and the
// progress-toast helper (``beginProgressToast``) compute the *same* curve
// and the same human-readable remaining-time string. Keeping it as pure
// functions (no Vue, no i18n) makes the behaviour trivially testable and
// reusable from a Pinia store, a component, or a plain module alike.

export const PROGRESS_HEAD_START_PCT = 8
export const PROGRESS_AT_ESTIMATE_PCT = 80
export const PROGRESS_CEILING_PCT = 98

export interface PercentCurveOptions {
  /** Where the bar jumps to immediately for perceived responsiveness. */
  headStart?: number
  /** Where the bar sits once 1× the estimate has elapsed. */
  atEstimate?: number
  /** Asymptotic ceiling — never reached, so an over-running op still
   *  shows forward motion instead of a stuck-full bar. */
  ceiling?: number
}

// Map elapsed/estimate onto a 0..ceiling percentage. Fills linearly to
// ``atEstimate`` at 1× the estimate, then decays asymptotically toward
// ``ceiling``. Never returns 100 — the caller snaps to 100 itself the
// moment the work actually completes (so the snap reads as "done").
export function estimatedPercent(
  elapsedMs: number,
  estimateMs: number,
  opts: PercentCurveOptions = {},
): number {
  const headStart = opts.headStart ?? PROGRESS_HEAD_START_PCT
  const atEstimate = opts.atEstimate ?? PROGRESS_AT_ESTIMATE_PCT
  const ceiling = opts.ceiling ?? PROGRESS_CEILING_PCT
  if (!Number.isFinite(estimateMs) || estimateMs <= 0) return headStart
  const x = Math.max(0, elapsedMs) / estimateMs
  const value =
    x < 1
      ? headStart + (atEstimate - headStart) * x
      : atEstimate + (ceiling - atEstimate) * (1 - Math.exp(-(x - 1) * 0.8))
  return Math.min(ceiling, Math.round(value))
}

// Whole seconds left until the estimate elapses, or ``null`` once we've
// overrun it. Past the estimate we genuinely don't know how much longer
// the op will take, so callers show an indeterminate "almost done" hint
// rather than a misleading (or negative) countdown.
export function remainingSeconds(elapsedMs: number, estimateMs: number): number | null {
  if (!Number.isFinite(estimateMs) || estimateMs <= 0) return null
  const remainingMs = estimateMs - Math.max(0, elapsedMs)
  if (remainingMs <= 0) return null
  return Math.ceil(remainingMs / 1000)
}

// Compact, locale-agnostic duration: "45 s", "2 min 10 s", "1 h 05 min".
// The units (h / min / s) read identically in FR and EN, so the formatter
// stays out of i18n; only the surrounding sentence ("~{time} remaining")
// is translated.
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds))
  if (s < 60) return `${s} s`
  const minutes = Math.floor(s / 60)
  const seconds = s % 60
  if (minutes < 60) {
    return seconds === 0 ? `${minutes} min` : `${minutes} min ${String(seconds).padStart(2, '0')} s`
  }
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  return `${hours} h ${String(mins).padStart(2, '0')} min`
}
