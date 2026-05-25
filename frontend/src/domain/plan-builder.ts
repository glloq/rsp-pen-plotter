// Single source of truth for "what layers does the backend see?".
//
// Before this module existed, ``runPreflight`` and ``generate`` each
// rebuilt their own ``payload.layers.map(...)`` from ``LayerInfo`` —
// three copies of the same projection. Adding a new field meant
// editing three places, with no compiler help if you missed one.
//
// Now every call site routes through ``toLayerPlan`` /
// ``buildPrintPlan``, so the projection is defined once and the
// TypeScript types from ``api-types.ts`` flag any new field that
// hasn't been propagated.

import type { LayerInfo } from '../api/client'
import type { LayerPlan, PlacementPlan, PrintPlan } from './print-plan'

/** Project a ``LayerInfo`` (editor state) to a backend ``LayerPlan``. */
export function toLayerPlan(layer: LayerInfo): LayerPlan {
  return {
    layer_id: layer.layer_id,
    target_pen_slot: layer.target_pen_slot,
    drawing_speed_mm_s: layer.drawing_speed_mm_s,
    source_color: layer.source_color,
    color_label: layer.color_label,
    pause_before: layer.pause_before,
    // ``optimize`` / ``simplify_tolerance_mm`` are operator-controlled
    // per-layer settings already consumed by the upstream /optimize call
    // (see runGeneratePipeline). We forward them into the plan so that
    // the resolved snapshot, the plan_hash and any future in-pipeline
    // optimizer all observe the same intent.
    optimize: layer.optimize,
    simplify_tolerance_mm: layer.simplify_tolerance_mm,
  }
}

export interface PrintPlanInputs {
  svg: string
  profileName: string
  layers: readonly LayerInfo[]
  placement: PlacementPlan | null
  scaleMode?: PrintPlan['scale_mode']
  marginMm?: number
  clientVersion?: string
}

/**
 * Build the ``PrintPlan`` sent to ``/preflight`` and ``/generate``.
 *
 * The same instance flows to both endpoints, which (combined with
 * the resolver-only backend path) guarantees a single ``plan_hash``
 * for both calls — see ``backend/pen_plotter/application/plan_resolver.py``.
 */
export function buildPrintPlan(inputs: PrintPlanInputs): PrintPlan {
  return {
    svg: inputs.svg,
    profile_name: inputs.profileName,
    layers: inputs.layers.map(toLayerPlan),
    scale_mode: inputs.scaleMode ?? 'actual',
    margin_mm: inputs.marginMm ?? 0,
    placement: inputs.placement,
    metadata: {
      client_version: inputs.clientVersion,
      created_at: new Date().toISOString(),
    },
  }
}
