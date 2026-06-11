// Debounced /preview round-trip scheduler. Extracted from
// SourceSection.vue's inline copy so:
//   - the same logic can drive the per-pass preview thumbnails added
//     later in the LayerPassStack refactor
//   - the watcher in SourceSection no longer needs to list every
//     individual field of BitmapDraft by hand (the 25-entry source
//     of "ajouter un slider = oublier d'ajouter au watcher" bugs)
//
// Behaviour mirrors the original:
//   - ``schedule({ immediate: true })`` skips the 500 ms debounce; used
//     by the detail-tier picker where one click is a single discrete
//     commitment, not a slider stream
//   - in-flight controller is aborted on every new run so the latest
//     parameters always win
//   - cancel() aborts AND clears the pending timeout so a torn-down
//     modal doesn't keep eating CPU
//
// The composable does NOT own the source ref / options builder /
// algorithm choice — those live in SourceSection and are passed in as
// arguments. Keeping the composable I/O-free makes it trivial to wire
// up to any preview-driving form, not just the bitmap one.

import { computed, ref } from 'vue'
import { previewBitmap, previewText, type PreviewResponse } from '../api/client'
import { sanitizeSvgCached } from '../lib/sanitizeSvg'

export interface PreviewSchedulerOptions {
  // Returns the current file to preview, or null when there's nothing
  // valid to send (e.g. the user hasn't attached a bitmap yet).
  fileGetter: () => File | null
  // Returns the current algorithm name. Mirrors the
  // ``bitmap.algorithm`` field SourceSection passes today.
  algorithmGetter: () => string
  // Returns the full options dict to ship with /preview. Same shape
  // as ``buildOptions()`` in SourceSection — a dict the backend's
  // ``BitmapOptions.model_validate`` understands.
  optionsBuilder: () => Record<string, unknown> | undefined
  // Returns true when the current source warrants a /preview call
  // (e.g. ``kind === 'bitmap'``). The scheduler defers entirely to
  // the caller for the "is bitmap?" decision so document / typography
  // modes can share the same composable later without leaking
  // kind-specific logic in here.
  shouldRun: () => boolean
  // Returns the operator-selected preview quality tier (draft /
  // standard / final). Forwarded to the API client and ends up as a
  // /preview form field plus part of the backend cache key.
  qualityGetter?: () => 'draft' | 'standard' | 'final'
  // i18n-resolved fallback message used when the network error has no
  // human-readable string of its own. Passed in (rather than
  // constructed in the composable) so this file doesn't pull in
  // vue-i18n.
  failedMessage?: string
  // i18n-resolved message used specifically when axios reports a
  // timeout (heavy style + high detail). Kept distinct from the
  // generic ``failedMessage`` so the UI can guide the operator to
  // lower the detail tier or hit Apply rather than chase a
  // mystery error.
  timeoutMessage?: string
  // Debounce window, ms. Matches the SourceSection default. Exposed
  // so per-pass thumbnails (added in Phase 3) can use a longer window
  // if needed.
  debounceMs?: number
  // Selects which backend endpoint feeds the preview. ``'bitmap'`` hits
  // ``/preview`` (k-means + per-cluster algorithm); ``'text'`` hits
  // ``/preview-text`` (Hershey single-stroke layout). The scheduler
  // shape stays identical — the same debounce / abort / staleness
  // guards apply to both paths.
  modeGetter?: () => 'bitmap' | 'text'
}

export function usePreviewScheduler(opts: PreviewSchedulerOptions) {
  const previewResult = ref<PreviewResponse | null>(null)
  const previewLoading = ref<boolean>(false)
  const previewError = ref<string | null>(null)
  let controller: AbortController | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  // Monotonic request counter. Belt-and-suspenders on top of the
  // AbortController — if a stale response somehow slips past the
  // signal check (e.g. browser flushes the resolved promise before the
  // abort propagates, or future callers invoke run() concurrently
  // without the lexical-closure guarantee we rely on today), the
  // revision compare drops it before it can clobber the latest result.
  let latestRevision = 0
  // No progress toast here: the scheduler only runs while the edit
  // modal is open (``shouldRun`` guard in useFileManager), where
  // EditPreviewPane already shows a loading overlay with a progress
  // bar — the bottom-right toast just duplicated it.

  const previewSvg = computed<string>(() => {
    if (!previewResult.value) return ''
    return sanitizeSvgCached(previewResult.value.svg)
  })

  async function run(): Promise<void> {
    const file = opts.fileGetter()
    if (!file || !opts.shouldRun()) return
    if (controller) controller.abort()
    const c = new AbortController()
    controller = c
    const myRevision = ++latestRevision
    previewLoading.value = true
    previewError.value = null
    try {
      const mode = opts.modeGetter?.() ?? 'bitmap'
      let result: PreviewResponse
      if (mode === 'text') {
        const textResult = await previewText(file, opts.optionsBuilder(), c.signal)
        // Shim the typography response into the PreviewResponse shape so
        // downstream consumers (EditPreviewPane, palette swatch strip)
        // don't need to branch on mode — typography has no palette and
        // no elapsed-ms metric to report.
        result = {
          svg: textResult.svg,
          elapsed_ms: 0,
          palette: [],
          warnings: textResult.truncated ? ['Preview truncated to the first 256 KB of text.'] : [],
          cached: false,
        }
      } else {
        result = await previewBitmap(
          file,
          opts.algorithmGetter(),
          opts.optionsBuilder(),
          c.signal,
          opts.qualityGetter?.() ?? 'standard',
        )
      }
      // Two-layer staleness guard: abort signal AND revision compare.
      // The revision check protects against a resolved promise being
      // flushed before the abort has propagated, or future callers
      // that bypass the controller swap.
      if (c.signal.aborted || myRevision !== latestRevision) return
      previewResult.value = result
    } catch (err) {
      if (c.signal.aborted || myRevision !== latestRevision) return
      const e = err as { code?: string; message?: string }
      // axios's own timeout path is no longer hit (we set timeout: 0)
      // but keep the categorisation defensive in case a downstream
      // proxy / fetch shim surfaces one anyway.
      const isTimeout =
        e.code === 'ECONNABORTED' || (typeof e.message === 'string' && /timeout/i.test(e.message))
      if (isTimeout && opts.timeoutMessage) {
        previewError.value = opts.timeoutMessage
      } else {
        previewError.value = e.message || opts.failedMessage || 'preview failed'
      }
    } finally {
      // Identity guard: a superseded run A must not clear the loading
      // flag belonging to the newer run B (B took over the controller
      // slot when it started).
      if (controller === c) {
        controller = null
        previewLoading.value = false
      }
    }
  }

  function schedule(o: { immediate?: boolean } = {}): void {
    const file = opts.fileGetter()
    if (!file || !opts.shouldRun()) return
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    if (o.immediate) {
      void run()
    } else {
      timer = setTimeout(() => {
        timer = null
        void run()
      }, opts.debounceMs ?? 500)
    }
  }

  function cancel(): void {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    if (controller) {
      controller.abort()
      controller = null
    }
    // Bump revision so any in-flight promise that already crossed the
    // ``aborted`` race window is still rejected by the staleness guard.
    latestRevision++
    previewLoading.value = false
  }

  function retry(): void {
    previewError.value = null
    void run()
  }

  // Clear the result (used post-upload when the placement's committed
  // SVG should take over from any stale draft preview).
  function clear(): void {
    previewResult.value = null
    previewError.value = null
  }

  return {
    previewResult,
    previewLoading,
    previewError,
    previewSvg,
    schedule,
    cancel,
    retry,
    clear,
    dispose: cancel,
  }
}
