// Progress-toast helper — the reusable "show a long operation with an ETA"
// primitive (audit AXE A, Phase 1).
//
// Wraps the toast store's ``progress`` channel with:
//   - a live, ticking remaining-time suffix + determinate bar derived from
//     a duration estimate (``estimatedPercent`` / ``remainingSeconds``),
//   - an optional ``showAfterMs`` so a *fast* operation never flashes a
//     toast at all — the toast only appears once the op is slow enough to
//     warrant feedback (mirrors the editor's 350 ms SSE-open threshold),
//   - a Cancel action button wired to the caller's abort hook,
//   - terminal ``succeed`` / ``fail`` / ``dismiss`` that resolve the toast.
//
// Implemented as a plain factory (not a Vue composable) so it works from a
// Pinia store action, a component, or any module — it owns its own timers
// and never relies on a Vue effect scope for cleanup.

import { i18n } from '../i18n'
import { useToastStore, type ToastAction } from '../stores/toasts'
import { estimatedPercent, formatDuration, remainingSeconds } from './progressEstimate'

// Cadence of the ETA refresh. 500 ms keeps the remaining-time readout
// lively without churning the reactive toast list every frame.
const TICK_MS = 500

export interface ProgressToastOptions {
  /** Base status line, e.g. "Updating render…". The remaining-time suffix
   *  is appended automatically when an estimate is supplied. */
  message: string
  /** Expected duration in ms. When > 0 the toast shows a determinate bar
   *  and a "~N s remaining" countdown; otherwise it's a plain spinner. */
  estimateMs?: number
  /** Defer creating the toast by this many ms. If the op finishes first,
   *  no toast is ever shown (no flash for fast operations). 0 = immediate. */
  showAfterMs?: number
  /** Abort hook. When provided, a Cancel button is wired onto the toast. */
  cancel?: () => void
  /** Override the Cancel button label (defaults to ``toast.cancel``). */
  cancelLabel?: string
}

export interface ProgressToastHandle {
  /** Replace the base status line (the ETA suffix is re-appended). */
  setMessage(message: string): void
  /** Feed REAL progress (0..100, optional layer label) from a streaming
   *  source. Supersedes the estimate: the bar switches to the real
   *  percent (seeded from where the estimate had it so it never jumps
   *  backward, then monotonic) and the message shows the label instead of
   *  the ETA. Does not force a deferred toast to appear — a fast op that
   *  finishes before ``showAfterMs`` still stays silent. */
  setProgress(percent: number, label?: string): void
  /** Resolve as success. Silent if the toast was deferred and never shown
   *  (a fast success needs no confirmation toast). */
  succeed(message: string, ttl?: number): void
  /** Resolve as error. Always surfaces — shows a fresh error toast even if
   *  the progress toast was never displayed. */
  fail(message: string, ttl?: number): void
  /** Tear down silently (cancelled / completed-without-message). */
  dismiss(): void
}

export function beginProgressToast(options: ProgressToastOptions): ProgressToastHandle {
  const toasts = useToastStore()
  const estimate = options.estimateMs && options.estimateMs > 0 ? options.estimateMs : 0
  const startedAt = Date.now()

  let baseMessage = options.message
  let id: number | null = null
  let ticker: ReturnType<typeof setInterval> | null = null
  let showTimer: ReturnType<typeof setTimeout> | null = null
  let settled = false
  // Real-progress state (driven by ``setProgress`` from a streaming source).
  let realActive = false
  let realLabel = ''
  let displayPct = 0

  function composeMessage(): string {
    if (realActive) {
      // Real per-layer progress: the bar carries the magnitude, the label
      // says which layer — no fabricated countdown.
      return realLabel ? `${baseMessage} · ${realLabel}` : baseMessage
    }
    if (!estimate) return baseMessage
    const remaining = remainingSeconds(Date.now() - startedAt, estimate)
    const suffix =
      remaining !== null
        ? i18n.global.t('toast.remaining', { time: formatDuration(remaining) })
        : i18n.global.t('toast.almostDone')
    return `${baseMessage} · ${suffix}`
  }

  // The percentage to paint right now: real progress once it's arrived,
  // otherwise the estimate curve (undefined → indeterminate spinner).
  function currentPercent(): number | undefined {
    if (realActive) return displayPct
    return estimate ? estimatedPercent(Date.now() - startedAt, estimate) : undefined
  }

  function open(): void {
    if (settled || id !== null) return
    const action: ToastAction | undefined = options.cancel
      ? {
          label: options.cancelLabel ?? i18n.global.t('toast.cancel'),
          onClick: () => options.cancel?.(),
        }
      : undefined
    id = toasts.progress(composeMessage(), action, currentPercent())
    // Animate while estimating; once real progress takes over,
    // ``currentPercent`` returns the (static-between-ticks) real value and
    // the same ticker just keeps the message fresh.
    if (estimate) {
      ticker = setInterval(() => {
        if (id === null) return
        toasts.setProgress(id, { percent: currentPercent(), message: composeMessage() })
      }, TICK_MS)
    }
  }

  function stopTimers(): void {
    if (showTimer !== null) {
      clearTimeout(showTimer)
      showTimer = null
    }
    if (ticker !== null) {
      clearInterval(ticker)
      ticker = null
    }
  }

  if (options.showAfterMs && options.showAfterMs > 0) {
    showTimer = setTimeout(() => {
      showTimer = null
      open()
    }, options.showAfterMs)
  } else {
    open()
  }

  return {
    setMessage(message: string): void {
      if (settled) return
      baseMessage = message
      if (id !== null) toasts.setProgress(id, { message: composeMessage() })
    },
    setProgress(percent: number, label?: string): void {
      if (settled) return
      const clamped = Math.max(0, Math.min(99, percent))
      if (!realActive) {
        realActive = true
        // Seed from where the estimate had the bar so switching to real
        // data never makes the bar jump backwards.
        displayPct = estimate ? estimatedPercent(Date.now() - startedAt, estimate) : 0
      }
      displayPct = Math.max(displayPct, clamped)
      if (label !== undefined) realLabel = label
      // Don't force a deferred toast open here — slow-only still holds.
      if (id !== null) toasts.setProgress(id, { percent: displayPct, message: composeMessage() })
    },
    succeed(message: string, ttl = 3000): void {
      if (settled) return
      settled = true
      stopTimers()
      // Only confirm if the toast was actually shown — a fast op that
      // never crossed ``showAfterMs`` shouldn't pop a success toast.
      if (id !== null) toasts.update(id, 'success', message, ttl)
    },
    fail(message: string, ttl = 6000): void {
      if (settled) return
      settled = true
      stopTimers()
      if (id !== null) toasts.update(id, 'error', message, ttl)
      else toasts.error(message, ttl)
    },
    dismiss(): void {
      if (settled) return
      settled = true
      stopTimers()
      if (id !== null) {
        toasts.dismiss(id)
        id = null
      }
    },
  }
}
