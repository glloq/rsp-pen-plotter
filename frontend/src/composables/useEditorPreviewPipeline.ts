// Single preview scheduler for the V2 editor modal.
//
// Extracted from ``EditModalV2.vue`` (Phase 1 of the editor audit). It
// replaces the four independent watchers + three debounce timers + the
// shared ``AbortController`` the modal grew with one entry point —
// ``schedule(level)`` — backed by a single timer and a single in-flight
// request.
//
// Invalidation levels, weakest → strongest:
//   - ``render-only``         : re-run /rerender with the current decision
//                               (ink assignment, custom-style stack, size).
//   - ``segment-and-render``  : re-check the palette segmentation, then
//                               render (kept for completeness / future use).
//   - ``resolve-and-segment`` : re-run the policy resolver, then segment,
//                               then render (intent / palette / pool change).
//
// Bursts that arrive within the debounce window collapse to ONE flush at
// the STRONGEST level requested — a slider scrub and a pool edit in the
// same beat resolve once, not twice. ``immediate`` bypasses the debounce
// for direct operator actions (mount, intent click) while still clearing
// any pending debounced flush, so an immediate request can't race a
// debounced one into a double render.
import { ref, type ComputedRef, type Ref } from 'vue'
import { resolveAlgorithmPolicy } from '../domain/policy/client'
import type { Goal, PaletteMode, PolicyDecision, PolicyPass, SourceKind } from '../domain/policy/schemas'
import { useJobStore } from '../stores/job'

export type PreviewInvalidation = 'render-only' | 'segment-and-render' | 'resolve-and-segment'

const LEVEL_RANK: Record<PreviewInvalidation, number> = {
  'render-only': 0,
  'segment-and-render': 1,
  'resolve-and-segment': 2,
}

// The resolver inputs that don't live on the pipeline's own refs —
// sourced from the modal's props at flush time so the resolve always
// sees the latest placement.
export interface PreviewResolveInputs {
  available_colors_count: number
  image_megapixels: number | null
  layer_count_estimate: number
  is_mono_pen_machine: boolean
}

export interface PreviewPipelineDeps {
  hasPlacement: Ref<boolean> | ComputedRef<boolean>
  sourceKind: Ref<SourceKind>
  goal: Ref<Goal>
  paletteMode: Ref<PaletteMode>
  customStylesActive: Ref<boolean> | ComputedRef<boolean>
  customPasses: Ref<PolicyPass[]> | ComputedRef<PolicyPass[]>
  resolveInputs: () => PreviewResolveInputs
  ensureSegmentation: (
    decision: PolicyDecision | null,
    controller: AbortController,
    onUploadStart: () => void,
  ) => Promise<void>
  /** Debounce window for non-immediate schedules. Defaults to 300 ms. */
  debounceMs?: number
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export function useEditorPreviewPipeline(deps: PreviewPipelineDeps) {
  const job = useJobStore()
  const debounceMs = deps.debounceMs ?? 300

  // Owned reactive state — the modal reads these for its template.
  const decision = ref<PolicyDecision | null>(null)
  const resolving = ref(false)
  const resolveError = ref<string | null>(null)
  const renderedSvg = ref<string | null>(null)
  const previewLoading = ref(false)
  const previewError = ref(false)

  let controller: AbortController | null = null
  let pending: PreviewInvalidation | null = null
  let timer: ReturnType<typeof setTimeout> | null = null

  function clearTimer(): void {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  function schedule(level: PreviewInvalidation, opts: { immediate?: boolean } = {}): void {
    // Escalate to the strongest level requested since the last flush.
    if (pending === null || LEVEL_RANK[level] > LEVEL_RANK[pending]) pending = level
    // Always drop any in-flight timer so an immediate request supersedes a
    // pending debounced one (and a fresh debounce restarts the window).
    clearTimer()
    if (opts.immediate) {
      void flush()
    } else {
      timer = setTimeout(() => {
        timer = null
        void flush()
      }, debounceMs)
    }
  }

  // Render-only path: re-run /rerender across every layer with the
  // current decision (or the operator's custom-style stack when active).
  // ``null`` means nothing renderable — fall back to the original
  // placement SVG so a stale render never lingers.
  async function render(c: AbortController): Promise<void> {
    if (!decision.value) return
    previewLoading.value = true
    try {
      const passes: PolicyPass[] = deps.customStylesActive.value
        ? deps.customPasses.value
        : (decision.value.default_passes ?? [])
      const result = passes.length
        ? await job.previewPassesOnAllLayers(passes, c.signal)
        : await job.previewAlgorithmOnAllLayers(
            decision.value.default_algorithm,
            (decision.value.default_options ?? {}) as Record<string, unknown>,
            c.signal,
          )
      if (c.signal.aborted) return
      renderedSvg.value = result ? result.svg : null
    } catch {
      if (!c.signal.aborted) previewError.value = true
    } finally {
      if (!c.signal.aborted) previewLoading.value = false
    }
  }

  async function flush(): Promise<void> {
    const level = pending
    pending = null
    if (level === null) return
    if (!deps.hasPlacement.value) return
    // Cancel any in-flight request so rapid toggles don't pile up stale
    // results — every flush owns exactly one AbortController.
    controller?.abort()
    const c = new AbortController()
    controller = c

    if (level === 'resolve-and-segment') {
      resolving.value = true
      resolveError.value = null
      previewError.value = false
      try {
        const d = await resolveAlgorithmPolicy({
          source_kind: deps.sourceKind.value,
          goal: deps.goal.value,
          palette_mode: deps.paletteMode.value,
          ...deps.resolveInputs(),
        })
        if (c.signal.aborted) return
        decision.value = d
      } catch (err) {
        resolveError.value = errorMessage(err)
        resolving.value = false
        return
      }
      resolving.value = false
      // Apply the decision's segmentation BEFORE rendering: /rerender only
      // re-inks the clusters the original /upload produced.
      await deps.ensureSegmentation(decision.value, c, () => {
        previewLoading.value = true
      })
      if (c.signal.aborted) return
      await render(c)
    } else if (level === 'segment-and-render') {
      if (!decision.value) return
      previewError.value = false
      await deps.ensureSegmentation(decision.value, c, () => {
        previewLoading.value = true
      })
      if (c.signal.aborted) return
      await render(c)
    } else {
      previewError.value = false
      await render(c)
    }
  }

  // Cancel the pending debounce and any in-flight request — call from the
  // host component's ``onBeforeUnmount``.
  function dispose(): void {
    clearTimer()
    controller?.abort()
  }

  return {
    decision,
    resolving,
    resolveError,
    renderedSvg,
    previewLoading,
    previewError,
    schedule,
    flush,
    dispose,
  }
}
