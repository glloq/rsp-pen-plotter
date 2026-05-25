# 0003 — Pydantic models at every API boundary

- **Status**: accepted
- **Date**: 2024-09 (back-dated)

## Context

FastAPI request bodies, the in-memory pivot (`PrintPlan` / `ResolvedPlan` /
`LayerPlan` / `TypographyPlan`), the configuration schemas
(`BitmapOptions` / `PreprocessOptions` / `MachineProfile`), the persistence
shape (jobs, audit log, library files) and the OpenAPI schema that drives
the TypeScript generator all need a single source of truth for "what does a
valid X look like".

The Python ecosystem offers a few options:

1. **Plain `@dataclass`.** Light, fast, no runtime validation.
2. **`attrs`.** Same shape as dataclasses with better ergonomics. Optional
   `attrs.validators`.
3. **Pydantic v2.** Type-driven validators, JSON serialization /
   deserialization, OpenAPI schema generation, native FastAPI integration.
4. **TypedDict + manual validators.** Cheapest, no machinery, but every
   boundary has to spell out its own validation.

## Decision

Use **Pydantic v2** as the single model layer:

- All API request / response bodies (`Layer`, `LayerPlan`, `PrintPlan`,
  `ResolvedPlan`, `BitmapOptions`, `MachineProfile`, every `/jobs`, `/files`,
  `/preflight`, `/generate` payload).
- The pivot types live in `domain/`: `print_plan.py`, `resolved_plan.py`,
  `typography_plan.py`. Each is a Pydantic model.
- Persistence rows that round-trip through SQLite use **SQLModel**
  (Pydantic-compatible) so the API model and the row schema share a
  declaration. See [ADR 0004](./0004-sqlite.md).
- Internal helper structures that never cross a boundary use `@dataclass`
  (lighter — e.g. `converters/bitmap/cache.py`'s `SegmentationResult`).

## Consequences

### Positive

- **Validation at the door.** Every FastAPI endpoint validates input before
  the handler runs; bad payloads return a structured 422 with a `detail`
  array pointing at the offending field. No hand-written guards.
- **OpenAPI for free.** `app.openapi()` emits a schema we feed into
  `openapi-typescript` to generate `frontend/src/domain/api-types.ts`. The
  frontend then talks to the backend with end-to-end-checked types.
- **Plan hashes from the model.** `ResolvedPlan.model_dump_json()` produces
  a deterministic JSON we hash; the same hash on /preflight and /generate
  guarantees the two endpoints agreed on what was about to be drawn.
- **Versioning + migrations are explicit.** Field additions in a Pydantic
  model surface as a single diff against the model class; the L4 lot
  hardened this for `BitmapOptions` (7 structured rerender reasons + a
  GET /files/integrity endpoint).
- **`field_validator` is where invariants live.** E.g. crop rectangle must
  lie within [0, 1] in `PreprocessOptions` (validated in one place, not
  scattered across the codebase).

### Negative

- **Startup cost.** Importing the model layer pulls in Pydantic v2's
  Rust-compiled core; cold start on a Pi is ~0.4s slower than a plain
  dataclass-only layer would be. Acceptable for a long-running service.
- **Strict mode bites occasionally.** `model_config = ConfigDict(extra="forbid")`
  on top-level options means a new client sending an unknown field gets a
  422 instead of a silent accept. We accepted this as the safer default;
  the alternative — silent acceptance — was the failure mode that bit us
  pre-L4.
- **mypy + Pydantic v2 wasn't perfectly smooth.** A few SQLModel-adjacent
  files carry per-file `ignore_errors` flags (`persistence.py`,
  `queue.py`). The L12 lot in the audit is dedicated to clearing those.
- **Some perf-critical hot paths skip Pydantic.** The bitmap converter's
  per-layer recipes pass plain `dict`s through `ProcessPoolExecutor`
  because Pydantic models aren't picklable across process boundaries
  without extra work. Plain dicts are documented at those call sites.

## What we don't use Pydantic for

- Internal dataclasses with no boundary crossing (`SegmentationResult`).
- Configuration that's never serialized (CLI args parsed with `argparse`).
- Hot-loop primitives that need to be pickled into worker pools.

## Alternatives we still reject

`@dataclass` + manual validators would mean re-implementing what
Pydantic's `field_validator` already does. We'd lose the OpenAPI
generation step entirely; the TypeScript types would have to be
hand-maintained (and they'd drift).

`attrs` has competitive ergonomics but no first-class FastAPI integration
and no OpenAPI generator. We'd be running two model layers (one for the
API, one for everything else) — exactly what this ADR is meant to avoid.
