// Progressive-preview stream wiring for the V2 editor preview pane.
//
// Extracted from ``EditPreviewPane.vue`` (Phase 4 of the editor audit). Owns
// the open/close lifecycle of the /preview/stream SSE connection plus the
// estimated determinate progress bar, and folds the two into a single
// ``displayPercent`` the loading overlay binds to. Kept as a composable so the
// "don't open for sub-350 ms previews" timing and the max(stream, estimate)
// merge are testable without mounting the pane (inject a stub stream + a stub
// estimated-progress handle and drive fake timers).
import { computed, onScopeDispose, watch } from 'vue'
import { useEstimatedProgress, type EstimatedProgress } from './useEstimatedProgress'
import { useProgressiveStream, type StreamHandle } from './useProgressiveStream'

// Previews that resolve faster than this never open an SSE connection — the
// plain spinner is fine and opening + closing a stream for a sub-second
// render is wasted work (plus the overlay flicker is annoying).
const SLOW_PREVIEW_MS = 350

export interface EditorPreviewStreamDeps {
  /** True while a /rerender is in flight. Drives both the stream open/close
   *  and the estimated progress bar. */
  loading: () => boolean
  /** Library file id of the active placement, or null/undefined when there's
   *  nothing to stream from (draft previews) — the stream stays closed then. */
  streamFileId: () => string | null | undefined
  /** Expected /preview latency in ms for the active algorithm × quality, used
   *  to animate the estimated bar. */
  estimateMs: () => number | null | undefined
}

export interface EditorPreviewStreamOptions {
  /** Stub stream handle for tests; defaults to a real ``useProgressiveStream``. */
  stream?: StreamHandle
  /** Stub estimated-progress handle for tests; defaults to a real
   *  ``useEstimatedProgress`` bound to the loading + estimate getters. */
  estimatedProgress?: EstimatedProgress
}

export function useEditorPreviewStream(
  deps: EditorPreviewStreamDeps,
  options: EditorPreviewStreamOptions = {},
) {
  const stream = options.stream ?? useProgressiveStream()
  const estimatedProgress =
    options.estimatedProgress ?? useEstimatedProgress(deps.loading, () => deps.estimateMs() ?? 0)

  let openTimer: ReturnType<typeof setTimeout> | null = null

  function shouldStream(): boolean {
    // Only open when we actually have a file id to stream from. Without one
    // the endpoint falls back to its synthetic emitter — not useful here.
    return Boolean(deps.streamFileId())
  }

  function clearOpenTimer(): void {
    if (openTimer !== null) {
      clearTimeout(openTimer)
      openTimer = null
    }
  }

  watch(deps.loading, (loading) => {
    if (loading && shouldStream()) {
      clearOpenTimer()
      // Capture the file id at schedule time so a prop swap mid-delay can't
      // sneak ``undefined`` into the URL.
      const scheduledFileId = deps.streamFileId()
      openTimer = setTimeout(() => {
        openTimer = null
        // Re-check at fire time: the parent may have invalidated the file
        // (placement removed) during the 350 ms window. Bail silently — the
        // plain spinner is fine.
        if (!scheduledFileId || scheduledFileId !== deps.streamFileId()) return
        const url = `/preview/stream?file_id=${encodeURIComponent(scheduledFileId)}`
        stream.open(url)
      }, SLOW_PREVIEW_MS)
    } else {
      clearOpenTimer()
      stream.close()
    }
  })

  // A pending setTimeout would otherwise still fire after teardown — opening
  // an EventSource after the stream's own cleanup already ran. Cancel the
  // timer on scope dispose, and close the stream explicitly so the contract
  // holds even when an injected ``StreamHandle`` doesn't tear itself down on
  // dispose (the real ``useProgressiveStream`` does, but the cleanup must not
  // depend on that implicit behaviour — audit P2).
  onScopeDispose(() => {
    clearOpenTimer()
    stream.close()
  })

  const streamLabel = computed<string>(() => {
    const payload = stream.lastProgress.value?.payload
    if (payload && typeof payload.layer_label === 'string') return payload.layer_label
    return ''
  })
  // Internal only — folded into ``displayPercent`` below; not part of the
  // public surface since the overlay binds the merged percent, not the raw
  // stream percent.
  const streamPercent = computed<number>(() => stream.percent.value ?? 0)
  const streamActive = computed<boolean>(() => Boolean(stream.active.value))

  // Merge the real stream percent with the estimated bar: while the stream is
  // reporting, show whichever is further along so real layer ticks can only
  // move the bar forward, never backwards. Without a stream the estimate
  // carries it alone (draft previews, single-band mono renders).
  const displayPercent = computed<number>(() =>
    streamActive.value
      ? Math.max(streamPercent.value, estimatedProgress.percent.value)
      : estimatedProgress.percent.value,
  )

  return { streamLabel, streamActive, displayPercent }
}
