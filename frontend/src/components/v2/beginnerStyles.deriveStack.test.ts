import { describe, expect, it } from 'vitest'
import {
  BEGINNER_STYLES,
  MAX_BEGINNER_STYLES,
  deriveBeginnerStack,
  getBeginnerStyle,
} from './beginnerStyles'

const CROSSHATCH = getBeginnerStyle('crosshatch')!
const STIPPLING = getBeginnerStyle('stippling')!

describe('deriveBeginnerStack', () => {
  it('returns [] for null / empty specs', () => {
    expect(deriveBeginnerStack(null)).toEqual([])
    expect(deriveBeginnerStack(undefined)).toEqual([])
    expect(deriveBeginnerStack({})).toEqual([])
  })

  it('maps a single committed algorithm to its beginner style + knob value', () => {
    const stack = deriveBeginnerStack({
      algorithm: 'crosshatch',
      algorithm_options: { [CROSSHATCH.primaryKnob.optionKey]: 2.4 },
    })
    expect(stack).toEqual([{ id: 'crosshatch', knobValue: 2.4 }])
  })

  it('falls back to the style default when the knob option is missing or non-numeric', () => {
    expect(deriveBeginnerStack({ algorithm: 'crosshatch', algorithm_options: {} })).toEqual([
      { id: 'crosshatch', knobValue: CROSSHATCH.primaryKnob.default },
    ])
    expect(
      deriveBeginnerStack({
        algorithm: 'crosshatch',
        algorithm_options: { [CROSSHATCH.primaryKnob.optionKey]: 'oops' },
      }),
    ).toEqual([{ id: 'crosshatch', knobValue: CROSSHATCH.primaryKnob.default }])
  })

  it('reconstructs a multi-pass stack, honouring pass order', () => {
    const stack = deriveBeginnerStack({
      algorithm: 'crosshatch',
      algorithm_options: {},
      passes: [
        { algorithm: 'crosshatch', algorithm_options: { [CROSSHATCH.primaryKnob.optionKey]: 1.2 } },
        { algorithm: 'stippling', algorithm_options: { [STIPPLING.primaryKnob.optionKey]: 0.5 } },
      ],
    })
    expect(stack).toEqual([
      { id: 'crosshatch', knobValue: 1.2 },
      { id: 'stippling', knobValue: 0.5 },
    ])
  })

  it('skips disabled passes', () => {
    const stack = deriveBeginnerStack({
      passes: [
        { algorithm: 'crosshatch', algorithm_options: {}, enabled: false },
        { algorithm: 'stippling', algorithm_options: {} },
      ],
    })
    expect(stack.map((s) => s.id)).toEqual(['stippling'])
  })

  it('returns [] when any step is outside the beginner catalogue', () => {
    // ``flowfield`` is a real algorithm but not one of the curated chips.
    expect(deriveBeginnerStack({ algorithm: 'flowfield' })).toEqual([])
    expect(
      deriveBeginnerStack({
        passes: [
          { algorithm: 'crosshatch', algorithm_options: {} },
          { algorithm: 'flowfield', algorithm_options: {} },
        ],
      }),
    ).toEqual([])
  })

  it('caps the reconstructed stack at MAX_BEGINNER_STYLES', () => {
    const ids = BEGINNER_STYLES.slice(0, MAX_BEGINNER_STYLES + 2).map((s) => s.id)
    const stack = deriveBeginnerStack({
      passes: ids.map((id) => ({ algorithm: id, algorithm_options: {} })),
    })
    expect(stack).toHaveLength(MAX_BEGINNER_STYLES)
  })
})
