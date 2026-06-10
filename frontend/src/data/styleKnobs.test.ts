import { describe, expect, it } from 'vitest'
import {
  MONO_STYLE_DEFAULTS,
  MULTICOLOR_STYLE_DEFAULTS,
  masterStylesByMode,
} from './printRegistry'
import {
  MONO_STYLE_KNOBS,
  MULTICOLOR_STYLE_KNOBS,
  knobKeys,
  resolveStyleKnobConfig,
  styleKnobDefaults,
  type KnobDescriptor,
  type MasterStyleFamily,
} from './styleKnobs'
import en from '../locales/en.json'
import fr from '../locales/fr.json'

// The knob descriptors replaced the hand-coded per-style template
// blocks of MasterStyleParams.vue / MultiColorMasterStyleParams.vue.
// These tests pin two things:
//   1. Parity with the pre-refactor twins: per style, the same controls
//      in the same order with the same bounds/step (the EXPECTED_*
//      tables below are transcribed from the deleted template blocks).
//   2. Structural invariants: every key a descriptor references exists
//      in the style's *_STYLE_DEFAULTS entry (the renderer's fallback
//      chain), every label/hint key exists in both locales, and the
//      registry default value sits inside the slider bounds.

function describeControl(c: KnobDescriptor): string {
  switch (c.kind) {
    case 'dual-range':
      return `dual:${c.keyMin}..${c.keyMax}:${c.min}..${c.max}@${c.step}`
    case 'range':
      return `range:${c.key}:${c.min}..${c.max}@${c.step}`
    case 'checkbox':
      return `check:${c.key}`
    case 'angle-set':
      return `angles:${c.key}:[${c.choices.join(',')}]max${c.maxSelected}`
  }
}

function inventory(family: MasterStyleFamily, styleId: string): string[] | undefined {
  const config = resolveStyleKnobConfig(family, styleId)
  if (!config) return undefined
  if (config.placeholderKey) return ['placeholder']
  return config.controls.map(describeControl)
}

// Transcribed 1:1 from the deleted template blocks of
// MasterStyleParams.vue (724-line version). Styles absent from this
// table (e.g. gosper-fill, the 2026-06 tonal masters) had no bespoke
// block and rendered the schema-driven AlgoParamsForm fallback — they
// must keep resolving to "no descriptor set".
const ANGLES = 'angles:angles:[0,30,45,90,135,150]max4'
const EXPECTED_MONO: Record<string, string[]> = {
  pencil: [ANGLES, 'dual:spacing_min..spacing_max:1..10@0.5', 'check:crossed_on_darkest'],
  'hatch-fill': [ANGLES, 'dual:spacing_min..spacing_max:1..10@0.5', 'check:crossed_on_darkest'],
  scribble: [ANGLES, 'dual:spacing_min..spacing_max:1..10@0.5', 'check:crossed_on_darkest'],
  'halftone-shade': ['dual:cell_min..cell_max:2..14@1'],
  'stippling-shade': ['dual:density_min..density_max:0.005..0.5@0.002', 'range:dot_radius:0.3..1.5@0.05'],
  'voronoi-shade': ['dual:density_min..density_max:0.005..0.5@0.002', 'range:dot_radius:0.3..1.5@0.05'],
  engraving: [
    'dual:spacing_min..spacing_max:1..8@0.5',
    'dual:wave_min..wave_max:0..3@0.1',
    'range:wave_period:8..20@1',
  ],
  'squiggle-shade': [
    'dual:spacing_min..spacing_max:1..8@0.5',
    'dual:wave_min..wave_max:0..3@0.1',
    'range:wave_period:8..20@1',
  ],
  'contours-topo': ['dual:spacing_min..spacing_max:1..8@0.5', 'dual:rings_min..rings_max:5..40@1'],
  'concentric-rings': ['dual:spacing_min..spacing_max:1..10@1', 'dual:rings_min..rings_max:2..80@1'],
  lowpoly: ['dual:density_min..density_max:0.002..0.1@0.002'],
  'flowfield-master': ['dual:spacing_min..spacing_max:1..20@0.5'],
  'hilbert-fill': ['dual:spacing_min..spacing_max:1..20@0.5'],
  tsp: ['range:density:0.01..0.1@0.005'],
  'tsp-optimized': ['range:density:0.01..0.1@0.005'],
  'spiral-master': [
    'range:spacing_px:3..30@1',
    'range:wavelength_px:2..24@1',
    'range:tone_strength:0..1@0.05',
  ],
  outline: ['range:stroke_width:0.4..2@0.1'],
  'centerline-trace': ['range:stroke_width:0.4..2@0.1'],
}

// Transcribed 1:1 from the deleted template blocks of
// MultiColorMasterStyleParams.vue (1099-line version).
const EXPECTED_MULTI: Record<string, string[]> = {
  'color-flat': ['placeholder'],
  'color-flat-lab': ['placeholder'],
  'color-crosshatch': [
    'dual:spacing_min..spacing_max:1..10@0.5',
    'range:angle_step:0..90@5',
    'check:crossed',
  ],
  'color-stipple': [
    'dual:density_min..density_max:0.005..0.3@0.001',
    'range:dot_radius:0.3..1.5@0.05',
    'range:iterations:0..20@1',
  ],
  'color-halftone-cmyk': ['range:cell_size:2..14@1'],
  'color-contours-topo': [
    'dual:spacing_min..spacing_max:1..8@0.5',
    'dual:rings_min..rings_max:5..40@1',
  ],
  'color-flowfield': [
    'dual:seed_spacing_min..seed_spacing_max:2..30@0.5',
    'range:step_px:0.2..3@0.1',
    'range:max_steps:100..2000@50',
    'range:noise_scale:4..128@2',
    'check:bidirectional',
  ],
  'color-sketch': [
    'dual:spacing_min..spacing_max:1..10@0.5',
    'dual:amp_min..amp_max:0.2..4@0.1',
    'range:period_px:2..20@0.5',
    'range:jitter:0..1@0.05',
  ],
  'color-spiral': ['dual:spacing_min..spacing_max:1..8@0.5', 'range:max_rings:5..120@1'],
  'color-stippling-classic': [
    'dual:density_min..density_max:0.005..0.3@0.001',
    'range:dot_radius:0.3..1.5@0.05',
  ],
  'color-edges': ['range:stroke_width:0.4..2@0.1'],
  'color-centerline': ['range:stroke_width:0.4..2@0.1', 'range:min_branch_px:1..20@1'],
  'color-spiral-classic': [
    'dual:spacing_min..spacing_max:1..8@0.5',
    'range:samples_per_turn:16..256@4',
  ],
  'color-scanlines': [
    'dual:spacing_min..spacing_max:1..10@0.5',
    'range:wave_amp_px:0..6@0.2',
    'range:wave_period_px:2..40@1',
  ],
  'color-tsp': ['dual:density_min..density_max:0.005..0.3@0.001'],
  'color-hilbert': ['dual:spacing_min..spacing_max:1..10@0.5', 'range:min_run_px:1..20@1'],
  'color-gosper': ['range:order:1..6@1', 'dual:spacing_min..spacing_max:1..8@0.5'],
  'color-eulerian': [
    'dual:spacing_min..spacing_max:1..10@0.5',
    'range:angle_step:0..90@5',
    'check:crossed',
  ],
  'color-tsp-opt': [
    'dual:density_min..density_max:0.005..0.3@0.001',
    'range:max_points:500..20000@500',
    'range:time_budget_s:0.2..6@0.1',
  ],
  'color-grid': ['dual:spacing_min..spacing_max:1..20@0.5'],
  'color-brick': ['dual:cell_min..cell_max:2..30@1'],
  'color-dashes': [
    'dual:spacing_min..spacing_max:1..10@0.5',
    'range:angle_step:0..90@5',
    'range:dash_px:0.5..12@0.5',
    'range:gap_px:0.5..12@0.5',
  ],
  'color-truchet': ['dual:cell_min..cell_max:2..30@1'],
  'color-rings': ['dual:spacing_min..spacing_max:1..20@0.5'],
  'color-sunburst': ['dual:rays_min..rays_max:8..360@4'],
  'color-circle-pack': ['dual:radius_min..radius_max:2..20@0.5', 'range:gap_px:0..6@0.1'],
}

function i18nHas(dict: Record<string, unknown>, key: string): boolean {
  let node: unknown = dict
  for (const part of key.split('.')) {
    if (typeof node !== 'object' || node === null) return false
    node = (node as Record<string, unknown>)[part]
  }
  return typeof node === 'string'
}

describe('styleKnobs', () => {
  it('matches the pre-refactor mono knob inventory exactly', () => {
    const actual: Record<string, string[]> = {}
    for (const id of Object.keys(MONO_STYLE_KNOBS)) {
      actual[id] = inventory('mono', id)!
    }
    expect(actual).toEqual(EXPECTED_MONO)
  })

  it('matches the pre-refactor multicolour knob inventory exactly', () => {
    const actual: Record<string, string[]> = {}
    for (const id of Object.keys(MULTICOLOR_STYLE_KNOBS)) {
      actual[id] = inventory('multicolor', id)!
    }
    expect(actual).toEqual(EXPECTED_MULTI)
  })

  it('resolves every registry master style without throwing', () => {
    for (const style of masterStylesByMode('monochrome')) {
      expect(() => resolveStyleKnobConfig('mono', style.id)).not.toThrow()
    }
    for (const style of masterStylesByMode('multicolor')) {
      expect(() => resolveStyleKnobConfig('multicolor', style.id)).not.toThrow()
    }
  })

  it('only declares descriptors for styles that exist in the registry', () => {
    const monoIds = new Set(masterStylesByMode('monochrome').map((s) => s.id))
    for (const id of Object.keys(MONO_STYLE_KNOBS)) {
      expect(monoIds, `mono descriptor for unknown style ${id}`).toContain(id)
    }
    const multiIds = new Set(masterStylesByMode('multicolor').map((s) => s.id))
    for (const id of Object.keys(MULTICOLOR_STYLE_KNOBS)) {
      expect(multiIds, `multicolor descriptor for unknown style ${id}`).toContain(id)
    }
  })

  it('keeps gosper-fill (and other fallback-only styles) descriptor-free', () => {
    // Tone for gosper-fill is the L-system order lerped by the registry
    // bandRecipe — it intentionally renders the AlgoParamsForm fallback.
    expect(resolveStyleKnobConfig('mono', 'gosper-fill')).toBeUndefined()
  })

  const families: Array<
    [MasterStyleFamily, Record<string, import('./styleKnobs').StyleKnobConfig>]
  > = [
    ['mono', MONO_STYLE_KNOBS],
    ['multicolor', MULTICOLOR_STYLE_KNOBS],
  ]

  for (const [family, table] of families) {
    describe(`${family} descriptors`, () => {
      it('reference only knob keys present in the style defaults', () => {
        const defaultsTable = family === 'mono' ? MONO_STYLE_DEFAULTS : MULTICOLOR_STYLE_DEFAULTS
        for (const [styleId, config] of Object.entries(table)) {
          for (const ctl of config.controls) {
            for (const key of knobKeys(ctl)) {
              expect(
                defaultsTable[styleId],
                `${family}/${styleId} has no defaults entry but descriptors reference ${key}`,
              ).toBeDefined()
              expect(
                Object.prototype.hasOwnProperty.call(defaultsTable[styleId], key),
                `${family}/${styleId}: descriptor key ${key} missing from defaults`,
              ).toBe(true)
            }
          }
        }
      })

      it('keep the registry default values inside the slider bounds', () => {
        for (const [styleId, config] of Object.entries(table)) {
          const defaults = styleKnobDefaults(family, styleId)
          for (const ctl of config.controls) {
            if (ctl.kind !== 'dual-range' && ctl.kind !== 'range') continue
            for (const key of knobKeys(ctl)) {
              const v = defaults[key]
              expect(typeof v, `${family}/${styleId}.${key} default`).toBe('number')
              expect(v as number, `${family}/${styleId}.${key} below slider min`).greaterThanOrEqual(
                ctl.min,
              )
              expect(v as number, `${family}/${styleId}.${key} above slider max`).lessThanOrEqual(
                ctl.max,
              )
            }
          }
        }
      })

      it('use i18n keys present in both locales', () => {
        for (const [styleId, config] of Object.entries(table)) {
          const keys: string[] = []
          if (config.introHintKey) keys.push(config.introHintKey)
          if (config.placeholderKey) keys.push(config.placeholderKey)
          for (const ctl of config.controls) {
            keys.push(ctl.labelKey)
            if ('hintKey' in ctl && ctl.hintKey) keys.push(ctl.hintKey)
          }
          for (const key of keys) {
            expect(i18nHas(en, key), `${family}/${styleId}: en missing ${key}`).toBe(true)
            expect(i18nHas(fr, key), `${family}/${styleId}: fr missing ${key}`).toBe(true)
          }
        }
      })
    })
  }
})
