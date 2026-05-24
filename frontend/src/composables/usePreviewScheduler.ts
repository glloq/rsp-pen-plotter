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
import DOMPurify from 'dompurify'
import { previewBitmap, type PreviewResponse } from '../api/client'

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
  // i18n-resolved fallback message used when the network error has no
  // human-readable string of its own. Passed in (rather than
  // constructed in the composable) so this file doesn't pull in
  // vue-i18n.
  failedMessage?: string
  // Debounce window, ms. Matches the SourceSection default. Exposed
  // so per-pass thumbnails (added in Phase 3) can use a longer window
  // if needed.
  debounceMs?: number
}

export function usePreviewScheduler(opts: PreviewSchedulerOptions) {
  const previewResult = ref<PreviewResponse | null>(null)
  const previewLoading = ref<boolean>(false)
  const previewError = ref<string | null>(null)
  let controller: AbortController | null = null
  let timer: ReturnType<typeof setTimeout> | null = null

  const previewSvg = computed<string>(() => {
    if (!previewResult.value) return ''
    return DOMPurify.sanitize(previewResult.value.svg, {
      USE_PROFILES: { svg: true, svgFilters: true },
    })
  })

  async function run(): Promise<void> {
    const file = opts.fileGetter()
    if (!file || !opts.shouldRun()) return
    if (controller) controller.abort()
    const c = new AbortController()
    controller = c
    previewLoading.value = true
    previewError.value = null
    try {
      const result = await previewBitmap(
        file,
        opts.algorithmGetter(),
        opts.optionsBuilder(),
        c.signal,
      )
      if (c.signal.aborted) return
      previewResult.value = result
    } catch (err) {
      if (c.signal.aborted) return
      previewError.value = (err as Error).message || opts.failedMessage || 'preview failed'
    } finally {
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
