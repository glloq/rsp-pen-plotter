// Legacy master-style knob payload conversion (2026-06 physical-units
// migration).
//
// Master-style knob payloads (``mono_knobs`` / ``multicolor_knobs`` in a
// placement's persisted ``last_options``) historically carried lengths
// in raster pixels: suffix-less fields (``spacing_min`` …) were
// px-scale values feeding ``*_px`` algorithm options, and a few fields
// carried an explicit ``_px`` suffix. The knob engine is now
// millimetre-based end to end, so payloads saved before the migration
// must be rescaled once at rehydration time — otherwise a saved
// ``spacing_min: 2.5`` (= 0.93 mm at the A4 reference scale) would be
// read as 2.5 mm and render ~2.7× sparser than the operator tuned it.
//
// Detection uses the ``knob_units: 'mm'`` marker the payload builder
// now writes; payloads without it are px-era and get converted.

/** Raster-pixel → millimetre factor at the A4 reference scale the
 *  whole migration uses (800 px segmentation canvas long side mapped
 *  onto an A4 long side, 297 mm). Mirrors the backend's
 *  ``A4_LONG_SIDE_MM`` fallback in ``_style.convert_mm_options``. */
export const PX_TO_MM = 297 / 800

/** Marker value written into knob payloads since the migration. */
export const KNOB_UNITS_MM = 'mm'

// Suffix-less knob fields that hold lengths (now interpreted as mm).
const LENGTH_FIELDS = new Set([
  'spacing_min',
  'spacing_max',
  'seed_spacing_min',
  'seed_spacing_max',
  'cell_min',
  'cell_max',
  'radius_min',
  'radius_max',
  'amp_min',
  'amp_max',
  'dot_radius',
  'cell_size',
  'wave_min',
  'wave_max',
  'wave_period',
])

// px-era field names that were renamed to their ``_mm`` twin.
const RENAMED_FIELDS: Record<string, string> = {
  step_px: 'step_mm',
  period_px: 'period_mm',
  wave_amp_px: 'wave_amp_mm',
  wave_period_px: 'wave_period_mm',
  min_branch_px: 'min_branch_mm',
  min_run_px: 'min_run_mm',
  dash_px: 'dash_mm',
  gap_px: 'gap_mm',
  spacing_px: 'spacing_mm',
  wavelength_px: 'wavelength_mm',
}

function round2(v: number): number {
  return Math.round(v * 100) / 100
}

/**
 * Convert one style's px-era knob bag into the mm scale. Non-length
 * fields (densities, counts, angles, seeds, nested override maps) pass
 * through untouched; unknown keys are preserved so nothing the operator
 * saved is dropped.
 */
export function convertLegacyStyleKnobs(
  knobs: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(knobs)) {
    const renamed = RENAMED_FIELDS[key]
    if (renamed && typeof value === 'number') {
      out[renamed] = round2(value * PX_TO_MM)
      continue
    }
    if (LENGTH_FIELDS.has(key) && typeof value === 'number') {
      out[key] = round2(value * PX_TO_MM)
      continue
    }
    out[key] = value
  }
  return out
}

/** True when a persisted knob payload pre-dates the mm migration. */
export function isLegacyKnobPayload(payload: Record<string, unknown>): boolean {
  return payload.knob_units !== KNOB_UNITS_MM
}
