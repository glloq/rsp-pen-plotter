# Codebase Audit

A full read-only audit of the backend (FastAPI/Python) and frontend
(Vue 3 + TypeScript) was performed, followed by the fixes recorded below.

## Verdict

The architecture is clean and consistently respected. A converter
plugin/registry layer normalizes every input to a single SVG pivot, after which
one format-agnostic pipeline (layer extraction → vpype optimization →
profile-driven G-code/EBB) runs identically for all inputs. Type coverage is
near `mypy --strict`-complete, security posture is solid (DOMPurify on rendered
SVG, server-side SVG sanitization, basename-only upload paths, subprocess calls
confined to temp dirs with no shell), and there were no TODOs, stubs, or dead
code in the core modules.

The findings were small, concrete improvements plus two test gaps and some
documentation drift — no architectural defects.

## Findings and fixes

| # | Area | Finding | Fix |
| --- | --- | --- | --- |
| 1 | `hardware/transport.py` | `SerialTransport.close()` closed the writer without awaiting `wait_closed()`, risking a leaked fd on quick reconnect | Await `wait_closed()` (suppressed) |
| 2 | `core/layers.py` ↔ `core/gcode.py` | Labeled-group detection was duplicated in `extract_layers` and `_read_layers` | Extracted `labeled_group_fragments()` as the single source of truth; both call it |
| 3 | `api/plotter.py` | `_profile_or_404` carried the only `# type: ignore[no-untyped-def]` | Annotated `-> MachineProfile`; ignore removed |
| 4 | `models.py` | `EbbConfig` fields had no documented units or bounds | Added `Field(description=…)` and positivity bounds |
| 5 | `components/SvgPreview.vue` | Hardcoded English placeholder string | Routed through i18n (`preview.placeholder`) |
| 6 | `components/LayerCard.vue` | Hardcoded `title="Drag to reorder"` | Uses existing `layers.dragHint` key |
| 7 | `stores/plotter.ts` | Unguarded `JSON.parse` in the WebSocket handler | Wrapped in try/catch; malformed frames ignored |
| 8 | `locales/*.json` | New string needed in both languages | Added `preview.placeholder` to `en` and `fr` |
| 9 | tests | `typography/hershey.py` had no tests | Added `tests/test_hershey.py` |
| 10 | tests | `api/plotter.py` connected-path endpoints were thinly covered | Added `tests/test_plotter_api.py` |
| 11 | docs | README structure listed nonexistent files and omitted real ones; `docs/` files referenced by README were missing | Reconciled README tree; authored this `docs/` set |

## Deliberately not changed

- The broad `except Exception` in `core/layers.py::_measure` guards a
  third-party geometry library (`svgelements`) that can raise many unrelated
  exception types; narrowing it would risk regressions. Left as justified
  defensive code.
- `gcode_dialect` is a constrained `Literal`, so an "unknown dialect" cannot
  reach `/generate`; all non-`ebb` values legitimately render via the template
  path. No validation added.

## Verification

- Backend: `ruff check` clean, `mypy` (strict) clean, `pytest` 98 passed.
- Frontend: `vitest` passed, `vue-tsc --noEmit` + `vite build` succeeded with no
  new `any`.
