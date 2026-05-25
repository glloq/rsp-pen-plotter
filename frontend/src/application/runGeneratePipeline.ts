// The composite optimize → preflight → generate pipeline, lifted out
// of ``stores/job.ts`` so it can be unit-tested without spinning up
// the whole Pinia store. The pipeline itself owns no state — the
// store passes in callbacks for the things it needs to keep in sync
// (placement patching, progress notifications, abort handling).

import { errorDetail } from '../api/error'
import {
  asMissingPenSlots,
  generateGcode,
  optimizeToolpaths,
  preflightCheck,
  type LayerInfo,
  type MissingPenSlotsDetail,
  type PreflightReport,
  type ToolpathMetrics,
} from '../api/client'
import { i18n } from '../i18n'
import type { PrintPlan } from '../domain/print-plan'

type Phase = 'optimize' | 'preflight' | 'generate'

export interface PipelinePlacement {
  id: string
  svg: string
  layers: LayerInfo[]
}

export interface OptimizeOutcome {
  svg: string
  layers: LayerInfo[]
  metrics: ToolpathMetrics
}

export interface GeneratePipelineDeps {
  /** Snapshot of placements at pipeline start. */
  placements: readonly PipelinePlacement[]
  /** Apply the post-optimize patch back to the store. */
  applyOptimized: (placementId: string, outcome: OptimizeOutcome) => void
  /** Re-build the composite ``PrintPlan`` after optimize has updated placements. */
  buildPlan: () => PrintPlan | null
  /** Notify the UI that a new phase started ("optimize" / "preflight" / "generate"). */
  onPhase: (phase: Phase) => void
  /** Surface the aggregate optimize metrics. */
  onMetrics: (metrics: ToolpathMetrics | null) => void
  /**
   * Ask the operator whether to generate despite missing pen slots.
   *
   * Called when /generate returns 409. Returning ``true`` retries the
   * call with ``allow_missing_slots=true``; returning ``false`` aborts
   * the pipeline with a localized error.
   */
  confirmMissingPenSlots?: (detail: MissingPenSlotsDetail) => Promise<boolean>
  /** External abort signal — cancels every in-flight request. */
  signal: AbortSignal
}

export interface GeneratePipelineOutcome {
  gcode: string
  preflight: PreflightReport
  planHash: string
}

export class PipelineAbortedError extends Error {
  constructor() {
    super('cancelled')
    this.name = 'PipelineAbortedError'
  }
}

/**
 * Run optimize → preflight → generate for the current scene.
 *
 * Throws :class:`PipelineAbortedError` if the signal fires. Any other
 * thrown error is unwrapped via ``errorDetail`` by the caller so the
 * UI can surface a localised message.
 */
export async function runGeneratePipeline(
  deps: GeneratePipelineDeps,
): Promise<GeneratePipelineOutcome> {
  if (deps.signal.aborted) throw new PipelineAbortedError()

  // --- optimize ---------------------------------------------------------
  deps.onPhase('optimize')
  const metrics = await optimizeAllPlacements(deps)
  deps.onMetrics(metrics)

  // --- preflight --------------------------------------------------------
  if (deps.signal.aborted) throw new PipelineAbortedError()
  deps.onPhase('preflight')
  const plan = deps.buildPlan()
  if (!plan) {
    throw new Error(i18n.global.t('layers.generateFailed'))
  }
  const preflight = await preflightCheck(plan, deps.signal)

  // --- generate ---------------------------------------------------------
  if (deps.signal.aborted) throw new PipelineAbortedError()
  deps.onPhase('generate')
  const generated = await tryGenerateWithSlotOverride(plan, deps)

  return {
    gcode: generated.gcode,
    preflight,
    planHash: generated.plan_hash,
  }
}

async function tryGenerateWithSlotOverride(
  plan: PrintPlan,
  deps: GeneratePipelineDeps,
): Promise<Awaited<ReturnType<typeof generateGcode>>> {
  try {
    return await generateGcode(plan, deps.signal)
  } catch (err) {
    const missing = asMissingPenSlots(err)
    if (!missing || !deps.confirmMissingPenSlots) throw err
    const proceed = await deps.confirmMissingPenSlots(missing)
    if (!proceed) throw err
    return await generateGcode(plan, deps.signal, { allowMissingSlots: true })
  }
}

async function optimizeAllPlacements(deps: GeneratePipelineDeps): Promise<ToolpathMetrics | null> {
  let beforeSum = 0
  let afterSum = 0
  let hasMetrics = false
  for (const placement of deps.placements) {
    if (deps.signal.aborted) throw new PipelineAbortedError()
    if (!placement.svg || !placement.layers.length) continue
    const result = await optimizeToolpaths(
      placement.svg,
      placement.layers.map((layer) => ({
        layer_id: layer.layer_id,
        optimize: layer.optimize,
        simplify_tolerance_mm: layer.simplify_tolerance_mm,
      })),
      deps.signal,
    )
    deps.applyOptimized(placement.id, {
      svg: result.svg,
      layers: result.layers,
      metrics: result.metrics,
    })
    beforeSum += result.metrics.pen_up_before_mm
    afterSum += result.metrics.pen_up_after_mm
    hasMetrics = true
  }
  if (!hasMetrics) return null
  const reduction = beforeSum > 0 ? ((beforeSum - afterSum) / beforeSum) * 100 : 0
  return {
    pen_up_before_mm: beforeSum,
    pen_up_after_mm: afterSum,
    reduction_pct: reduction,
  }
}

/** Lightweight error-classification helper so the store can pick a localized label. */
export function pipelineErrorMessage(phase: Phase, err: unknown): string {
  const fallback =
    phase === 'preflight'
      ? i18n.global.t('preflight.failed')
      : phase === 'optimize'
        ? i18n.global.t('layers.optimizeFailed')
        : i18n.global.t('layers.generateFailed')
  return errorDetail(err, fallback)
}
