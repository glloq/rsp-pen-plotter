import { beforeEach, describe, expect, it } from 'vitest'
import { buildTypographyPlan, defaultTypography, useBitmapDraft } from './useBitmapDraft'

describe('buildTypographyPlan', () => {
  beforeEach(() => {
    // The composable holds singleton refs; reset the typography draft
    // to its default between cases so mutations don't leak between
    // tests.
    useBitmapDraft().typo.value = defaultTypography()
  })

  it('returns null for vector / bitmap sources so the plan_hash stays unchanged', () => {
    // Non-text mimes ⇒ typography is irrelevant; emit null to preserve
    // backwards compat for every existing snapshot in the table.
    expect(buildTypographyPlan('image/png')).toBeNull()
    expect(buildTypographyPlan('image/svg+xml')).toBeNull()
    expect(buildTypographyPlan('image/jpeg')).toBeNull()
    expect(buildTypographyPlan(null)).toBeNull()
    expect(buildTypographyPlan(undefined)).toBeNull()
  })

  it('emits the current TypographyDraft for text sources', () => {
    // Mutate the singleton draft directly (the EditModal does this via
    // v-model on the TypographyCard), then expect the projection to
    // mirror it field-for-field.
    const draft = useBitmapDraft()
    draft.typo.value.font = 'rowmant'
    draft.typo.value.font_size_mm = 18
    draft.typo.value.bold = true

    const plan = buildTypographyPlan('text/plain')
    expect(plan).not.toBeNull()
    expect(plan!.font).toBe('rowmant')
    expect(plan!.font_size_mm).toBe(18)
    expect(plan!.bold).toBe(true)
  })

  it('covers every text-source mime the backend hershey converters handle', () => {
    // The set must stay in sync with the converters registered in
    // ``pen_plotter.converters.defaults`` — drift here means the
    // typography travels to the pivot for some inputs but not for
    // others, which is exactly the regression class this lot closes.
    for (const mime of [
      'text/plain',
      'text/markdown',
      'text/html',
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    ]) {
      expect(buildTypographyPlan(mime)).not.toBeNull()
    }
  })
})
