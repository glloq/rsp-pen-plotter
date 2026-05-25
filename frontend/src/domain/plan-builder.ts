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
import type { LayerPlan, PlacementPlan, PrintPlan, TypographyPlan } from './print-plan'

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
    assigned_color_hex: layer.assigned_color_hex,
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
  /**
   * Typography intent for text sources. Forwarded into the plan so the
   * persisted snapshot and the plan_hash both reflect the operator's
   * font / size / weight choices. Paired with ``libraryFileId`` +
   * ``sourceMime`` the backend re-renders the text source at /preflight
   * + /generate time from the original bytes — no re-upload needed.
   * See ``backend/pen_plotter/application/text_render.py``.
   */
  typography?: TypographyPlan | null
  /**
   * Reference to the original uploaded file in the library. When the
   * backend sees this paired with a ``typography`` block and a
   * recognised ``sourceMime``, it re-renders the text source from
   * those bytes so the operator's typography edits land without a
   * re-upload. ``null`` keeps the legacy upload-time render — the
   * plan's ``svg`` is used as-is.
   */
  libraryFileId?: string | null
  /**
   * MIME of the original library file. Required for the in-pipeline
   * text rerender path to engage; the backend uses it to route the
   * bytes back through the correct converter.
   */
  sourceMime?: string | null
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
    typography: inputs.typography ?? null,
    library_file_id: inputs.libraryFileId ?? null,
    source_mime: inputs.sourceMime ?? null,
    metadata: {
      client_version: inputs.clientVersion,
      created_at: new Date().toISOString(),
    },
  }
}
