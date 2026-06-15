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
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { resolveAlgorithmPolicy } from '../domain/policy/client'
import type {
  Goal,
  PaletteMode,
  PolicyDecision,
  PolicyPass,
  SourceKind,
} from '../domain/policy/schemas'
import { errorMessage } from '../lib/errorMessage'
import { useJobStore } from '../stores/job'

export type PreviewInvalidation = 'render-only' | 'segment-and-render' | 'resolve-and-segment'

// Single source of truth for "is the preview pipeline doing anything?".
// The modal disables Generate for every non-terminal state so the operator
// can't generate from a placement whose palette / segmentation / render
// hasn't caught up with their last click (audit P0 §2).
//   - ``idle``       : nothing in flight, the displayed render is current.
//   - ``resolving``  : the policy resolver is running.
//   - ``segmenting`` : re-uploading the placement to match the pool.
//   - ``rendering``  : /rerender (or /preview) is producing the SVG.
//   - ``error``      : the last flush failed; terminal until the next flush.
export type PipelineStatus = 'idle' | 'resolving' | 'segmenting' | 'rendering' | 'error'

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
  // Specific reason the last preview (segment / render) failed — surfaced
  // next to the generic "preview unavailable" message so a network drop
  // during re-segmentation reads as more than a frozen spinner.
  const previewErrorMessage = ref<string | null>(null)
  // Explicit lifecycle status (see ``PipelineStatus``). Drives the modal's
  // Generate-disabled guard so generation can't fire mid-pipeline.
  const status = ref<PipelineStatus>('idle')
  // True while the pipeline is mid-flight (resolving / segmenting /
  // rendering). ``error`` and ``idle`` are both "safe to generate" terminal
  // states — the operator can still generate from the last good placement
  // even if the *preview* couldn't be refreshed.
  const busy = computed(
    () =>
      status.value === 'resolving' || status.value === 'segmenting' || status.value === 'rendering',
  )

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
    } catch (err) {
      if (!c.signal.aborted) {
        previewError.value = true
        previewErrorMessage.value = errorMessage(err)
      }
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

    // Every phase below runs inside ONE try/finally so a throw from the
    // resolver OR ``ensureSegmentation`` (network drop, backend 500 during
    // re-upload) can never escape as an unhandled rejection or strand the
    // ``resolving`` / ``previewLoading`` flags at ``true`` — that was the
    // frozen-spinner / stuck-pipeline failure mode flagged in audit P0 §1.
    try {
      if (level === 'resolve-and-segment') {
        status.value = 'resolving'
        resolving.value = true
        resolveError.value = null
        previewError.value = false
        previewErrorMessage.value = null
        let resolved: PolicyDecision
        try {
          resolved = await resolveAlgorithmPolicy({
            source_kind: deps.sourceKind.value,
            goal: deps.goal.value,
            palette_mode: deps.paletteMode.value,
            ...deps.resolveInputs(),
          })
        } catch (err) {
          // A resolver failure is reported on its own channel
          // (``resolveError``) and aborts the flush before segmentation —
          // the static defaults still let the operator generate.
          if (!c.signal.aborted) {
            resolveError.value = errorMessage(err)
            status.value = 'error'
          }
          return
        }
        if (c.signal.aborted) return
        decision.value = resolved
        // Apply the decision's segmentation BEFORE rendering: /rerender only
        // re-inks the clusters the original /upload produced.
        status.value = 'segmenting'
        await deps.ensureSegmentation(decision.value, c, () => {
          previewLoading.value = true
        })
        if (c.signal.aborted) return
        status.value = 'rendering'
        await render(c)
      } else if (level === 'segment-and-render') {
        if (!decision.value) return
        previewError.value = false
        previewErrorMessage.value = null
        status.value = 'segmenting'
        await deps.ensureSegmentation(decision.value, c, () => {
          previewLoading.value = true
        })
        if (c.signal.aborted) return
        status.value = 'rendering'
        await render(c)
      } else {
        previewError.value = false
        previewErrorMessage.value = null
        status.value = 'rendering'
        await render(c)
      }
      // ``render`` swallows its own errors into ``previewError``; reflect
      // that in the terminal status so a failed render still disables the
      // "stale" spinner without claiming success.
      if (!c.signal.aborted) status.value = previewError.value ? 'error' : 'idle'
    } catch (err) {
      // Reached only when ``ensureSegmentation`` throws (resolver errors
      // return above, render errors are caught inside ``render``).
      if (!c.signal.aborted) {
        previewError.value = true
        previewErrorMessage.value = errorMessage(err)
        status.value = 'error'
      }
    } finally {
      // Release the per-flush flags so a failed or short-circuited run never
      // leaves a permanent spinner. A NEWER flush will have aborted this
      // controller and owns its own flags, so we skip the reset then.
      if (!c.signal.aborted) {
        resolving.value = false
        previewLoading.value = false
      }
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
    previewErrorMessage,
    status,
    busy,
    schedule,
    flush,
    dispose,
  }
}
