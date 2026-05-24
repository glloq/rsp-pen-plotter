// @deprecated — façade. Layer-scope print styles live in
// ``./printRegistry.ts`` now (scope='layer'). New code should import
// ``PRINT_STYLES`` / ``layerStyles`` from there directly.

import {
  layerStyles,
  type PrintStyle as RegPrintStyle,
  type PrintStyleKind,
} from './printRegistry'

export type { PrintStyleKind }

// Legacy ``PrintStyle`` shape exposed ``algorithm`` and
// ``algorithm_options`` directly. The registry stores them under
// ``defaultAlgorithm`` / ``defaultAlgorithmOptions`` so master + layer
// styles share the same field names. Adapt for backwards compat.
export interface PrintStyle {
  id: string
  labelKey: string
  descriptionKey?: string
  applicableTo: PrintStyleKind[]
  algorithm: string
  algorithm_options: Record<string, unknown>
}

function adapt(s: RegPrintStyle): PrintStyle {
  return {
    id: s.id,
    labelKey: s.labelKey,
    descriptionKey: s.descriptionKey,
    applicableTo: s.applicableTo,
    algorithm: s.defaultAlgorithm,
    algorithm_options: s.defaultAlgorithmOptions,
  }
}

export const PRINT_STYLES: PrintStyle[] = layerStyles().map(adapt)

export function stylesFor(kind: PrintStyleKind): PrintStyle[] {
  return layerStyles(kind).map(adapt)
}
