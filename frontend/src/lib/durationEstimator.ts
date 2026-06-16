// Persisted single-scalar EMA of an operation's wall-clock duration (ms),
// keyed by a string so several long ops each keep their own learned
// estimate. Mirrors ``usePreviewCostEstimator``'s "EMA in localStorage"
// approach, but for whole-operation durations (the generate pipeline, a
// system update…) where there's no per-(algorithm × quality) axis — just
// "how long did this op take the last few times". The first run has no
// sample, so callers fall back to an indeterminate indicator; every run
// after sharpens the ETA.

const STORAGE_KEY = 'omniplot.durationEstimates.v1'
// Adapt reasonably fast — a changed scene / device should move the
// estimate within a couple of runs, but a single jittery sample shouldn't
// yank it. Picked by eye, like the preview estimator's 0.3.
const EMA_ALPHA = 0.4
// Ignore implausibly short samples (early abort, no-op) so they don't
// poison the estimate for a genuinely long operation.
const MIN_SAMPLE_MS = 200

type Store = Record<string, number>

function load(): Store {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object') return parsed as Store
  } catch {
    /* corrupt or unavailable — start fresh */
  }
  return {}
}

function save(store: Store): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store))
  } catch {
    /* quota / unavailable — estimate is best-effort, never a correctness gate */
  }
}

/** Fold an observed duration (ms) into the EMA for ``key``. */
export function recordDuration(key: string, ms: number): void {
  if (!Number.isFinite(ms) || ms < MIN_SAMPLE_MS) return
  const store = load()
  const prev = store[key]
  const next = typeof prev === 'number' && prev > 0 ? prev * (1 - EMA_ALPHA) + ms * EMA_ALPHA : ms
  store[key] = Math.round(next)
  save(store)
}

/** Best current duration estimate (ms) for ``key``, or 0 when none yet. */
export function getDurationEstimateMs(key: string): number {
  const value = load()[key]
  return typeof value === 'number' && value > 0 ? value : 0
}
