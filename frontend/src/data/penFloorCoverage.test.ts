import { describe, expect, it } from 'vitest'
import { PRINT_STYLES, getAlgorithm } from './printRegistry'
import { MONO_STYLE_KNOBS, MULTICOLOR_STYLE_KNOBS } from './styleKnobs'
import { ALGO_PEN_FLOOR_KEYS } from '../lib/penWidth'

// "Verify every colour + monochrome style": any control that asks the
// operator for a physical dot/line size must be floored at the pen tip
// (you can't draw thinner than the pen). This pins that coverage so a
// newly-added style or algorithm that exposes a mark-size knob can't
// silently ship without the floor.
//
// Two surfaces, two flooring mechanisms:
//   - master-style descriptor RangeKnob → ``penFloor`` flag
//     (rendered by MasterStyleKnobs as a slider).
//   - generic AlgoParamsForm fallback → the schema option key must be
//     listed in ``ALGO_PEN_FLOOR_KEYS``.

// Knob-store keys / schema option keys that name a physical pen mark.
const DESCRIPTOR_MARK_KEYS = new Set(['dot_radius', 'stroke_width'])
const SCHEMA_MARK_KEYS = new Set(['dot_radius_mm', 'stroke_width'])

const masters = PRINT_STYLES.filter((s) => s.scope === 'master')

describe('pen-width floor coverage across all master styles', () => {
  it('floors every mark-size descriptor knob', () => {
    const unfloored: string[] = []
    for (const s of masters) {
      const family = s.mode === 'multicolor' ? 'multicolor' : 'mono'
      const cfg = (family === 'mono' ? MONO_STYLE_KNOBS : MULTICOLOR_STYLE_KNOBS)[s.id]
      if (!cfg) continue
      for (const ctl of cfg.controls) {
        if (ctl.kind !== 'range') continue
        if (DESCRIPTOR_MARK_KEYS.has(ctl.key) && !ctl.penFloor) {
          unfloored.push(`${family}/${s.id}.${ctl.key}`)
        }
      }
    }
    expect(unfloored, 'descriptor mark knobs missing penFloor').toEqual([])
  })

  it('floors every mark-size knob exposed via the generic fallback', () => {
    const unfloored: string[] = []
    for (const s of masters) {
      const family = s.mode === 'multicolor' ? 'multicolor' : 'mono'
      const cfg = (family === 'mono' ? MONO_STYLE_KNOBS : MULTICOLOR_STYLE_KNOBS)[s.id]
      if (cfg) continue // descriptor styles are covered by the test above
      const schema = getAlgorithm(s.defaultAlgorithm)?.schema ?? []
      for (const opt of schema) {
        if (SCHEMA_MARK_KEYS.has(opt.key) && !(opt.key in ALGO_PEN_FLOOR_KEYS)) {
          unfloored.push(`${family}/${s.id} → ${s.defaultAlgorithm}.${opt.key}`)
        }
      }
    }
    expect(unfloored, 'fallback mark knobs missing from ALGO_PEN_FLOOR_KEYS').toEqual([])
  })
})
