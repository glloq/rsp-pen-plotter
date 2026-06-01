# Codebase Audit (2026-06)

A full audit of the backend (FastAPI/Python, ~36k LOC) and frontend
(Vue 3 + TypeScript, ~50k LOC) for redundant code, dead code, logic
correctness, and coding-standard compliance. Automated tooling (ruff,
mypy --strict, eslint, vue-tsc, vulture, knip, pytest, vitest) was
combined with a manual subsystem-by-subsystem review. Findings were
verified individually (false positives are listed below). The fixes
applied in this pass are recorded in the *Fixed* section.

## Verdict

The architecture remains clean and consistently respected: a converter
plugin/registry layer normalizes every input to a single SVG pivot, after
which one format-agnostic pipeline (layer extraction → vpype optimization →
profile-driven G-code/EBB) runs identically for all inputs. Tests are
healthy (755 backend + 418 frontend) and the security posture is solid.

However, the previous audit's "mypy strict clean / no dead code" claim had
**drifted**: this pass found 6 real strict-typing regressions, three dead
frontend files, two unused npm dependencies, a duplicated MIME helper that
re-implemented an existing shared one, redundant in-function imports, a
no-op dead branch, and a concurrency hazard in the progress broadcaster.
No architectural defects.

## Tooling baseline (before fixes)

| Tool | Result |
| --- | --- |
| pytest / vitest / vue-tsc | green (755 / 418 / clean) |
| mypy (strict) | **6 errors** in 3 files |
| ruff | 6 errors (all in `tests/`) + one import-sort in `converters/html.py` |
| eslint | 0 errors, 65 warnings (`vue/no-mutating-props`) |

## Fixed in this pass

### Dead code

| # | Area | Finding | Fix |
| --- | --- | --- | --- |
| 1 | `components/v2/StepperHeader.vue` | Never imported anywhere | File removed |
| 2 | `components/v2/WorkspaceRail.vue` | Never imported (only comment refs); ~250 LOC | File removed |
| 3 | `composables/useDirtyTracker.ts` | Unwired "Phase 4" feature, never used | File removed |
| 4 | `frontend/package.json` | `svg-pan-zoom` (0 usages) and `@types/dompurify` (redundant — dompurify v3 ships its own types) | Both dependencies removed; lockfile updated |
| 5 | `core/pdf_postprocess.py` (orphaned `<defs>` cleanup) | `if child_id in targets and child_id not in [t for t in targets if t]: pass` — condition is always false and the body is empty | Replaced the loop with the equivalent `keep = any(not child.get("id") for child in defs)` |

### Redundant / duplicated code

| # | Area | Finding | Fix |
| --- | --- | --- | --- |
| 6 | `api/preview.py` + `api/preview_text.py` | `_resolve_mime` was duplicated in both, while `converters/pipeline.py::resolve_mime` already does exactly the same thing | Both copies deleted; both import the shared helper. Now-unused `import mimetypes` removed from both |
| 7 | `core/pdf_postprocess.py` | `import re` (×3) and `import math` (×3) repeated inside functions | Hoisted to a single module-level import each |
| 8 | `core/toolpath.py` | `from pen_plotter.observability import traced_span` imported inside two functions (no import cycle — verified) | Hoisted to a single module-level import |

### Type-correctness (mypy strict regressions)

| # | Area | Finding | Fix |
| --- | --- | --- | --- |
| 9 | `core/gcode.py` | `park_x`/`park_y` inferred `float` from `pen_change_point()` then reassigned `None` in sibling branches | Declared `park_x: float \| None` / `park_y: float \| None` before first binding |
| 10 | `core/pdf_postprocess.py` | `label` reused across two loops with incompatible types (`str` then `str \| None`) | Renamed the second binding to `child_label` |
| 11 | `typography/hershey.py` | `glyph.char_width * abs(scalex)` returned `Any` from an untyped font lib | Wrapped in `float(...)` |

### Logic / robustness

| # | Area | Finding | Fix |
| --- | --- | --- | --- |
| 12 | `hardware/controller.py::_broadcast` | Iterated over the `_subscribers` set with an `await` inside the loop; a concurrent `subscribe`/`unsubscribe` during that await could mutate the set mid-iteration (`RuntimeError: Set changed size`) | Iterate over a `list(self._subscribers)` snapshot; documented why |

### Standards / functional consistency

| # | Area | Finding | Fix |
| --- | --- | --- | --- |
| 13 | `algorithms/{scribble,centerline,edges,lowpoly}.py` | Hard-coded `float(opts.get("stroke_width", 0.8))`, bypassing the shared `stroke_attr_px()` helper that the 34 other algorithms use — so these four **ignored the injected physical pen width** | All four now call `stroke_attr_px(opts)`, honouring the per-layer pen width like the rest |
| 14 | `tests/test_pdf_postprocess.py` | `E741` ambiguous variable name `l` (×3) | Renamed to `lyr` |
| 15 | `typography/hershey.py` | `D301`: backslashes in a non-raw docstring | Made the docstring raw (`r"""`) |
| 16 | `converters/html.py`, `core/pdf_postprocess.py` | `I001`/`D202` import-sort and post-docstring blank lines | Auto-fixed by `ruff --fix` |

## Documented but not changed (out of selected scope)

The following were confirmed as real findings but deferred — they are
either larger refactors or were not selected for this pass:

- **`vue/no-mutating-props` (65 eslint warnings)** in `edit/source/TypographyCard.vue`,
  `edit/style/PostProcessCard.vue`, `edit/svg/SegmentationMethodCard.vue`. These
  components mutate a "draft" object passed as a prop. It works but deviates from
  the Vue convention; converting to explicit `update:*` events / `v-model` is a
  medium refactor of the editor.
- **`as any` casts** in `edit/render/MasterStyleParams.vue:82` and
  `MultiColorMasterStyleParams.vue:36` — the `setMonoKnob`/`setMulticolorKnob`
  composable signatures should expose a typed overload instead.
- **Near-duplicate logic** kept as-is pending a dedicated refactor:
  `strip_text_elements` (`core/svg_text_extract.py`) vs `strip_text_glyphs`
  (`core/pdf_postprocess.py`); `should_pause` vs `should_pause_ebb`
  (`core/pause_logic.py`); hex canonicalisation in `stores/job.ts` vs
  `lib/penWidth.ts`.
- **~20 raster algorithms** lack a `render_layer()` docstring (the class-level
  docstring is currently the canonical doc; ruff already exempts these via
  `per-file-ignores`).
- **Accessibility**: clickable `<div>` without keyboard role in
  `components/LayerCardSummary.vue:37`.
- **Repeated Tailwind/field markup** across `components/edit/*` — candidate for a
  shared `<NumberField>` / `<CardIntro>` component.
- **`api/files.py` back-compat aliases** `_svg_path`, `_file_dir` are unused
  (but `_find_original`/`_meta_path` *are* used by `tests/test_rerender_endpoint.py`,
  so the alias block stays). Trivial; left intentionally.
- **Pre-existing format drift** *not* enforced by CI: `ruff format` would
  reformat ~20 backend files (older formatting config) and `prettier` flags
  `components/AppHeader.vue` + `SwapPromptModal.vue`. CI enforces `ruff check`
  (lint, not format) on the backend and `prettier --check` on `src/**`. These
  drifts are unrelated to this pass and were left untouched to avoid noise.

## False positives ruled out (verification rigor)

- `core/toolchange.py:138` — `code` reported as a dead variable; it **is** used
  (`if not code: continue`).
- `api/files.py:115-117` — aliases reported as "never used"; `_find_original` and
  `_meta_path` are used by `tests/test_rerender_endpoint.py`, exactly as the
  comment states.
- Most "unused exports" flagged by knip (zod schemas in
  `domain/{capability,policy,manifests}/schemas.ts`) are intentional public
  surface or test-only usages, not dead code.

## Verification (after fixes)

- Backend: `ruff check` clean, `mypy` (strict) **clean** (0 errors, 155 files),
  `pytest` **755 passed**.
- Frontend: `vitest` **418 passed**, `vue-tsc --noEmit` clean, `vite build`
  succeeded.
