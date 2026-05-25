import { beforeEach, describe, expect, it } from 'vitest'
import { useBitmapDraft } from './useBitmapDraft'
import {
  buildTypographyOptions,
  buildTypographyPlan,
  defaultTypography,
  isTypographyDirty,
  markTypographyCommitted,
  rehydrateTypographyFromOptions,
  resetTypography,
  useTypographyDraft,
} from './useTypographyDraft'

// The typography composable is the L6 extraction of the typography
// slice that used to live in ``useBitmapDraft``. These tests pin down
// the standalone surface (defaults, rehydrate, dirty, commit, build
// helpers) AND the singleton-sharing contract with ``useBitmapDraft``:
// the EditModal binds against ``useBitmapDraft().typo`` and the file
// previewer watches it deep — both must keep seeing the same ref the
// new module owns.

describe('useTypographyDraft singleton contract', () => {
  beforeEach(() => {
    resetTypography()
    markTypographyCommitted()
  })

  it('exposes the same ref as useBitmapDraft().typo', () => {
    // The L6 split is invisible to ``useFileManager``'s deep watcher
    // and to TypographyCard's v-model only if both composables hand
    // out THE same singleton ref. Cross-mutate to prove it.
    const typo = useTypographyDraft()
    const bitmap = useBitmapDraft()
    expect(typo.typo).toBe(bitmap.typo)

    typo.typo.value.font = 'rowmant'
    expect(bitmap.typo.value.font).toBe('rowmant')

    bitmap.typo.value.font_size_mm = 24
    expect(typo.typo.value.font_size_mm).toBe(24)
  })

  it('reset() puts the singleton back to defaults', () => {
    const t = useTypographyDraft()
    t.typo.value.font = 'rowmant'
    t.typo.value.font_size_mm = 24
    t.typo.value.bold = true

    t.reset()
    expect(t.typo.value).toEqual(defaultTypography())
  })
})

describe('rehydrateTypographyFromOptions', () => {
  beforeEach(() => {
    resetTypography()
  })

  it('is a no-op when the placement has no last_options', () => {
    rehydrateTypographyFromOptions(null)
    rehydrateTypographyFromOptions(undefined)
    expect(useTypographyDraft().typo.value).toEqual(defaultTypography())
  })

  it('copies only declared TypographyDraft keys from the persisted blob', () => {
    rehydrateTypographyFromOptions({
      font: 'timesrb',
      font_size_mm: 22,
      alignment: 'right',
      letter_spacing_mm: 0.5,
      // Stray keys must be ignored — the rehydrate target is the
      // declared shape of TypographyDraft, not every key the
      // placement blob happens to ship.
      band_recipes: [{ algorithm: 'spiral' }],
      foo: 'bar',
    } as Record<string, unknown>)

    const t = useTypographyDraft().typo.value
    expect(t.font).toBe('timesrb')
    expect(t.font_size_mm).toBe(22)
    expect(t.alignment).toBe('right')
    expect(t.letter_spacing_mm).toBe(0.5)
    expect((t as Record<string, unknown>).band_recipes).toBeUndefined()
    expect((t as Record<string, unknown>).foo).toBeUndefined()
    // Missing keys keep the default — this is how older placements
    // that pre-date a newer typography field still hydrate cleanly.
    expect(t.margin_mm).toBe(defaultTypography().margin_mm)
  })
})

describe('isTypographyDirty / markTypographyCommitted', () => {
  beforeEach(() => {
    resetTypography()
    markTypographyCommitted()
  })

  it('returns false right after markTypographyCommitted', () => {
    expect(isTypographyDirty.value).toBe(false)
  })

  it('flips true when any field changes and back to false after a fresh commit', () => {
    const t = useTypographyDraft()
    t.typo.value.font = 'rowmant'
    expect(isTypographyDirty.value).toBe(true)

    markTypographyCommitted()
    expect(isTypographyDirty.value).toBe(false)
  })
})

describe('buildTypographyOptions', () => {
  beforeEach(() => {
    resetTypography()
  })

  it('returns a shallow copy that mirrors the live draft', () => {
    useTypographyDraft().typo.value.font = 'rowmans'
    const opts = buildTypographyOptions()
    expect(opts.font).toBe('rowmans')
    ;(opts as Record<string, unknown>).font = 'mutated'
    expect(useTypographyDraft().typo.value.font).toBe('rowmans')
  })
})

describe('buildTypographyPlan', () => {
  beforeEach(() => {
    resetTypography()
  })

  it('emits the projected plan for text mime types', () => {
    const t = useTypographyDraft()
    t.typo.value.font = 'rowmant'
    t.typo.value.font_size_mm = 18
    const plan = buildTypographyPlan('text/plain')
    expect(plan).not.toBeNull()
    expect(plan!.font).toBe('rowmant')
    expect(plan!.font_size_mm).toBe(18)
  })

  it('emits null for vector / bitmap mime types', () => {
    expect(buildTypographyPlan('image/png')).toBeNull()
    expect(buildTypographyPlan('image/svg+xml')).toBeNull()
    expect(buildTypographyPlan(null)).toBeNull()
    expect(buildTypographyPlan(undefined)).toBeNull()
  })
})
