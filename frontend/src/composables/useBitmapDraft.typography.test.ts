import { beforeEach, describe, expect, it } from 'vitest'
import {
  buildTypographyPlan,
  defaultTypography,
  useBitmapDraft,
  type TypographyDraft,
} from './useBitmapDraft'

// The composable is a module-level singleton: it survives across tests
// within the same Vitest worker. ``resetDraft`` puts every state field
// the typography lifecycle touches back to a known starting point so
// the lifecycle suites don't leak state between cases.
function resetDraft(): void {
  const d = useBitmapDraft()
  d.rehydrateDraft({ placement: null, installedPenColors: [] })
}

describe('buildTypographyPlan', () => {
  beforeEach(() => {
    resetDraft()
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

describe('typography defaults', () => {
  it('matches the Pydantic backend defaults so a fresh placement renders identically', () => {
    // Keep these in sync with ``defaultTypography`` AND the backend's
    // ``TypographyPlan`` defaults. Drift here is the regression class
    // that gave us "the modal looks empty but the upload renders 10mm
    // Sans at A4" reports.
    const d = defaultTypography()
    expect(d.font).toBe('futural')
    expect(d.font_size_mm).toBe(10)
    expect(d.line_spacing).toBe(1.5)
    expect(d.alignment).toBe('left')
    expect(d.stroke_width_mm).toBe(0.3)
    expect(d.margin_mm).toBe(15)
    expect(d.page_width_mm).toBe(210)
    expect(d.page_height_mm).toBe(297)
    expect(d.bold).toBe(false)
    expect(d.italic).toBe(false)
    expect(d.letter_spacing_mm).toBe(0)
    expect(d.hershey_text).toBe(true)
  })
})

describe('typography rehydrate lifecycle', () => {
  beforeEach(() => {
    resetDraft()
  })

  it('resets to defaults when rehydrate is called without persisted options', () => {
    // Operator opens a fresh placement (no last_options): every typo
    // field falls back to the pristine default rather than carrying
    // over whatever the previous placement had.
    const draft = useBitmapDraft()
    draft.typo.value.font = 'rowmant'
    draft.typo.value.font_size_mm = 24

    draft.rehydrateDraft({ placement: null, installedPenColors: [] })

    expect(draft.typo.value).toEqual(defaultTypography())
  })

  it('merges typography fields from last_options on rehydrate', () => {
    // Reopening the modal on an already-uploaded placement must show
    // the exact font / size / page / alignment that produced the
    // committed SVG. Unknown keys are ignored; missing keys keep
    // their default (older placements pre-dating a field still
    // hydrate cleanly).
    const draft = useBitmapDraft()
    draft.rehydrateDraft({
      placement: {
        last_options: {
          font: 'timesrb',
          font_size_mm: 22,
          alignment: 'center',
          hershey_text: true,
          bold: true,
          // Random unrelated key — must not pollute the draft.
          foo: 'bar',
        },
      },
      installedPenColors: [],
    })

    expect(draft.typo.value.font).toBe('timesrb')
    expect(draft.typo.value.font_size_mm).toBe(22)
    expect(draft.typo.value.alignment).toBe('center')
    expect(draft.typo.value.hershey_text).toBe(true)
    expect(draft.typo.value.bold).toBe(true)
    // Untouched fields stay at the default.
    expect(draft.typo.value.line_spacing).toBe(defaultTypography().line_spacing)
    expect(draft.typo.value.margin_mm).toBe(defaultTypography().margin_mm)
  })
})

describe('typography dirty tracking', () => {
  beforeEach(() => {
    resetDraft()
  })

  it('flips isDirty when any typography field is mutated', () => {
    // The EditModal disables Apply while isDirty is false; if typo
    // edits never reached the dirty tracker, the operator could change
    // the font and the button would stay grey.
    const draft = useBitmapDraft()
    draft.markCommitted()
    expect(draft.isDirty.value).toBe(false)

    draft.typo.value.font = 'rowmant'
    expect(draft.isDirty.value).toBe(true)
  })

  it('isDirty returns to false after markCommitted snapshots the new state', () => {
    const draft = useBitmapDraft()
    draft.markCommitted()
    draft.typo.value.font_size_mm = 42
    expect(draft.isDirty.value).toBe(true)

    draft.markCommitted()
    expect(draft.isDirty.value).toBe(false)
  })

  it('every typography knob participates in dirty tracking', () => {
    // Sentinel sweep: every field of TypographyDraft must affect the
    // dirty bit. A field that's silently dropped from the snapshot
    // would let the operator change it and exit the modal without a
    // warning. The values picked here are distinct from the defaults.
    const samples: Array<[keyof TypographyDraft, TypographyDraft[keyof TypographyDraft]]> = [
      ['font', 'rowmant'],
      ['font_size_mm', 42],
      ['line_spacing', 2.5],
      ['alignment', 'right'],
      ['stroke_width_mm', 0.9],
      ['margin_mm', 5],
      ['page_width_mm', 100],
      ['page_height_mm', 100],
      ['bold', true],
      ['italic', true],
      ['letter_spacing_mm', 1.5],
      ['hershey_text', false],
    ]
    const draft = useBitmapDraft()
    for (const [field, value] of samples) {
      resetDraft()
      draft.markCommitted()
      expect(draft.isDirty.value).toBe(false)
      ;(draft.typo.value as Record<string, unknown>)[field as string] = value
      expect(draft.isDirty.value, `mutating ${String(field)} should flip isDirty`).toBe(true)
    }
  })
})

describe('typography fields in buildBitmapOptions', () => {
  beforeEach(() => {
    resetDraft()
  })

  it('always ships font + stroke_width_mm so a later hershey toggle keeps the chosen face', () => {
    // ``font`` / ``stroke_width_mm`` travel with every /upload — even
    // when ``hershey_text`` is explicitly off, round-tripping a
    // placement must not silently reset the operator's font choice.
    const draft = useBitmapDraft()
    draft.typo.value.font = 'rowmant'
    draft.typo.value.stroke_width_mm = 0.55
    draft.typo.value.hershey_text = false

    const payload = draft.buildBitmapOptions()
    expect(payload.font).toBe('rowmant')
    expect(payload.stroke_width_mm).toBe(0.55)
    expect(payload.hershey_text).toBeUndefined()
  })

  it('emits hershey_text only when truthy', () => {
    // Truthy emits the flag; falsy omits it (matches the historic
    // wire shape the backend's bitmap-form options endpoint expects).
    const draft = useBitmapDraft()
    draft.typo.value.hershey_text = true
    const payload = draft.buildBitmapOptions()
    expect(payload.hershey_text).toBe(true)
  })
})

describe('buildTypographyOptions', () => {
  beforeEach(() => {
    resetDraft()
  })

  it('returns a shallow copy that mirrors the live draft', () => {
    const draft = useBitmapDraft()
    draft.typo.value.font = 'rowmans'
    draft.typo.value.font_size_mm = 14

    const opts = draft.buildTypographyOptions()
    expect(opts.font).toBe('rowmans')
    expect(opts.font_size_mm).toBe(14)
    // Shallow copy → mutating the returned object must not affect the
    // singleton (this is the contract the persistence layer relies on).
    ;(opts as Record<string, unknown>).font = 'mutated'
    expect(draft.typo.value.font).toBe('rowmans')
  })
})
