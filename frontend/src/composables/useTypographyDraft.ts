// Singleton owner of the EditModal's TypographyDraft — the slice of
// state that drives font face, size, alignment, page geometry and the
// Hershey re-render flag for .txt / .md / PDF / DOCX / HTML sources.
//
// Extracted from ``useBitmapDraft`` (L6) so the typography lifecycle
// (rehydrate ↔ dirty ↔ commit ↔ project-to-pivot) lives in a single
// focused module. ``useBitmapDraft`` re-exports the public surface
// (``TypographyDraft``, ``defaultTypography``, ``buildTypographyOptions``,
// ``buildTypographyPlan``) so existing callers — ``job.ts``, the
// EditModal, the typography tests — keep working without an import
// rewrite.
//
// The ref returned from ``useTypographyDraft().typo`` is the SAME
// singleton ref ``useBitmapDraft().typo`` returns. This matters for
// ``buildBitmapOptions`` (still ships ``font`` / ``stroke_width_mm`` /
// ``hershey_text`` on every /upload) and for the deep watcher in
// ``useFileManager`` that schedules ``/preview-text`` round-trips.

import { computed, ref, type ComputedRef, type Ref } from 'vue'

export type TypographyDraft = {
  font: string
  font_size_mm: number
  line_spacing: number
  alignment: 'left' | 'center' | 'right'
  stroke_width_mm: number
  margin_mm: number
  page_width_mm: number
  page_height_mm: number
  // Synthetic style toggles — Hershey fonts are single-stroke, so bold
  // double-passes each glyph with a small offset and italic shears every
  // point by ~12°. Letter spacing inserts extra millimeters between
  // characters; negative values tighten the rendering.
  bold: boolean
  italic: boolean
  letter_spacing_mm: number
  // When true on a PDF / DOCX / HTML source, the backend strips the
  // document's original glyph outlines and replays every text span
  // with single-stroke Hershey polylines at the same baseline
  // positions. Required for legible pen plotting of document text —
  // outline-traced TrueType glyphs paint as a double-traced silhouette
  // no pen can fill convincingly. Ignored on .txt / .md (those always
  // use Hershey).
  hershey_text: boolean
}

// Wire shape only; the actual TypographyPlan type lives in
// domain/print-plan.ts but importing it here would pull the OpenAPI
// types into the composable. Keeping a minimal local mirror avoids the
// cycle and the compiler still checks it against the call site.
export type TypographyPlanWire = {
  font: string
  font_size_mm: number
  page_width_mm: number
  page_height_mm: number
  margin_mm: number
  line_spacing: number
  alignment: 'left' | 'center' | 'right'
  stroke_width_mm: number
  bold: boolean
  italic: boolean
  letter_spacing_mm: number
}

export function defaultTypography(): TypographyDraft {
  return {
    font: 'futural',
    // 10 mm is the smallest body size that stays readable in the
    // simulator's default workspace-fit view. The Pydantic default
    // mirrors this — keep them in sync.
    font_size_mm: 10.0,
    line_spacing: 1.5,
    alignment: 'left',
    stroke_width_mm: 0.3,
    margin_mm: 15.0,
    page_width_mm: 210.0,
    page_height_mm: 297.0,
    bold: false,
    italic: false,
    letter_spacing_mm: 0.0,
    // Default ON: pen plotters can only trace strokes, so the document's
    // original TrueType glyph outlines paint as double-walled silhouettes
    // that no longer resemble letters once vpype strips the SVG fill.
    // Replaying each text span with single-stroke Hershey polylines is the
    // only legible default for PDF / DOCX / HTML sources. Ignored on
    // .txt / .md (TextConverter / MarkdownConverter always use Hershey).
    hershey_text: true,
  }
}

// Mime-type predicate kept here so the EditModal and the pipeline
// builder agree on what counts as a "text source" for typography
// purposes. Aligned with the backend's text-handling converters
// (text, markdown, html, docx, pdf). Exported so the job store's plan
// builder can locate the actual text placement in a mixed scene.
export function isTextSource(mime: string): boolean {
  return (
    mime.startsWith('text/') ||
    mime === 'application/pdf' ||
    mime === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    mime === 'text/html' ||
    mime === 'text/markdown'
  )
}

// ---- Singleton state ----
const _typo = ref<TypographyDraft>(defaultTypography())
const _baselineTypo = ref<string>('')

function snap(value: unknown): string {
  try {
    return JSON.stringify(value)
  } catch {
    return ''
  }
}

const _isTypographyDirty = computed<boolean>(() => snap(_typo.value) !== _baselineTypo.value)

// ---- Lifecycle helpers (consumed by ``useBitmapDraft``) ----

/**
 * Reset the typography draft to its pristine defaults. Called by
 * ``useBitmapDraft.rehydrateDraft`` before merging any persisted
 * ``last_options`` — guarantees a fresh placement opens with the
 * defaults instead of carrying over the previous placement's font.
 */
export function resetTypography(): void {
  _typo.value = defaultTypography()
}

/**
 * Merge the typography fields out of a placement's ``last_options``
 * payload over the current draft. Unknown keys are ignored; missing
 * keys keep whatever the draft already had (this is called right
 * after ``resetTypography``, so "missing" effectively means "default").
 *
 * Older placements pre-dating a recently added typography field still
 * hydrate cleanly because the merge only copies keys already declared
 * on ``TypographyDraft``.
 */
export function rehydrateTypographyFromOptions(
  opts: Record<string, unknown> | null | undefined,
): void {
  if (!opts || typeof opts !== 'object') return
  const target = _typo.value as Record<string, unknown>
  for (const key of Object.keys(target)) {
    if (key in opts) target[key] = opts[key]
  }
}

/**
 * Snapshot the current typography draft as the new committed
 * baseline. Called from ``useBitmapDraft.markCommitted`` after a
 * successful /upload (and from the rehydrate-and-mark path when the
 * placement carries committed options).
 */
export function markTypographyCommitted(): void {
  _baselineTypo.value = snap(_typo.value)
}

export const isTypographyDirty: ComputedRef<boolean> = _isTypographyDirty

export const typographyRef: Ref<TypographyDraft> = _typo

// ---- Public helpers (re-exported via useBitmapDraft for compat) ----

export function buildTypographyOptions(): Record<string, unknown> {
  return { ..._typo.value }
}

/**
 * Project the current TypographyDraft to the backend ``TypographyPlan``
 * shape so it can ride into the PrintPlan sent to /preflight + /generate.
 *
 * Returns ``null`` for non-text sources (the pivot stores ``null`` then;
 * the plan_hash stays identical to a vector / bitmap plan).
 *
 * Today the draft is a singleton: the EditModal works on one placement
 * at a time, so a multi-placement scene with several text sources falls
 * back to whichever draft was last touched. Tracking typography per
 * placement is a follow-up — for now this closes the regression where
 * font / size edits never reached the pivot at all.
 */
export function buildTypographyPlan(
  sourceMime: string | null | undefined,
): TypographyPlanWire | null {
  // Heuristic: text sources are the .txt / .md / docx / html / pdf
  // chain that the Hershey path can re-render. For images / SVG / DXF
  // the typography draft is irrelevant — emit null to keep their hash
  // identical to a vector / bitmap plan.
  if (!sourceMime || !isTextSource(sourceMime)) return null
  const t = _typo.value
  // ``alignment`` may be 'left' | 'center' | 'right' in the draft; the
  // backend pivot also accepts 'justify'. Pass through verbatim.
  return {
    font: t.font,
    font_size_mm: t.font_size_mm,
    page_width_mm: t.page_width_mm,
    page_height_mm: t.page_height_mm,
    margin_mm: t.margin_mm,
    line_spacing: t.line_spacing,
    alignment: t.alignment,
    stroke_width_mm: t.stroke_width_mm,
    bold: t.bold,
    italic: t.italic,
    letter_spacing_mm: t.letter_spacing_mm,
  }
}

// ---- Public composable ----
export function useTypographyDraft() {
  return {
    typo: _typo,
    isDirty: _isTypographyDirty,
    buildTypographyOptions,
    buildTypographyPlan,
    rehydrateFromOptions: rehydrateTypographyFromOptions,
    reset: resetTypography,
    markCommitted: markTypographyCommitted,
  }
}
