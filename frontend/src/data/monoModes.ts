// @deprecated — façade. Master-scope styles (the old "mono modes")
// live in ``./printRegistry.ts`` now (scope='master', with the same
// per-band recipe under ``bandRecipe``). New code should import
// ``masterStyles`` / ``getStyle`` / ``resolveMasterStyle`` from there.

import {
  DEFAULT_MASTER_STYLE_ID,
  LEGACY_MASTER_ID_MAP,
  getStyle,
  masterStyles,
  resolveMasterStyle,
  type PrintStyle as RegPrintStyle,
  type SegmentationMethod,
} from './printRegistry'

// Old segmentation type — kept narrow because the legacy mono modes
// only used these two methods. New code should use the wider
// ``SegmentationMethod`` from printRegistry.
export type SegmentationMethodMono = Extract<SegmentationMethod, 'luminance_bands' | 'thresholds'>

export interface MonoBandOverride {
  algorithm: string
  algorithm_options: Record<string, unknown>
}

// Legacy ``MonoMode`` shape — every consumer of monoModes.ts reaches
// for these exact fields. We adapt the registry entries on the fly so
// nothing breaks while ``MonochromeCard.vue`` / ``SourceSection.vue``
// still import from here.
export interface MonoMode {
  id: string
  labelKey: string
  descKey: string
  segmentation_method: SegmentationMethodMono
  default_bands: number
  default_threshold: number
  default_algorithm: string
  default_algorithm_options: Record<string, unknown>
  drop_background: boolean
  background_luminance: number
  knob_bands: boolean
  algoForBand: (i: number, total: number) => MonoBandOverride | null
}

function adapt(style: RegPrintStyle): MonoMode | null {
  const seg = style.segmentation
  if (!seg) return null
  if (seg.method !== 'luminance_bands' && seg.method !== 'thresholds') return null
  return {
    id: legacyIdFor(style.id),
    labelKey: style.labelKey,
    descKey: style.descriptionKey ?? '',
    segmentation_method: seg.method,
    default_bands: seg.default_num_bands ?? 2,
    default_threshold: seg.default_threshold ?? 0.5,
    default_algorithm: style.defaultAlgorithm,
    default_algorithm_options: style.defaultAlgorithmOptions,
    drop_background: seg.drop_background,
    background_luminance: seg.background_luminance,
    knob_bands: seg.knob_bands,
    algoForBand: (i, total) => style.bandRecipe?.(i, total) ?? null,
  }
}

// Reverse the registry's renamed ids back to the legacy mono mode ids
// so existing callers (and existing localStorage payloads) keep finding
// what they expect.
function legacyIdFor(registryId: string): string {
  for (const [legacy, modern] of Object.entries(LEGACY_MASTER_ID_MAP)) {
    if (modern === registryId) return legacy
  }
  return registryId
}

export const MONO_MODES: MonoMode[] = masterStyles()
  .map(adapt)
  .filter((m): m is MonoMode => m !== null)

export function getMonoMode(id: string): MonoMode | undefined {
  // Try direct lookup first (registry-style id), then legacy mapping.
  const direct = getStyle(id)
  if (direct?.segmentation) {
    const mode = adapt(direct)
    if (mode) return mode
  }
  const modernId = LEGACY_MASTER_ID_MAP[id]
  if (modernId) {
    const resolved = getStyle(modernId)
    if (resolved?.segmentation) {
      const mode = adapt(resolved)
      if (mode) return mode
    }
  }
  // Fall back to resolveMasterStyle which always returns the default —
  // matches the spirit of the old code that surfaced ``undefined`` so
  // callers can decide.
  return undefined
}

export const DEFAULT_MONO_MODE = legacyIdFor(DEFAULT_MASTER_STYLE_ID)

// Re-export the helpful resolver too so callers can opt into the new
// "always returns something" behaviour as they migrate.
export { resolveMasterStyle }
