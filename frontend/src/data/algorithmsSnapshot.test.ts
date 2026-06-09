import { describe, expect, it } from 'vitest'

import snapshot from './algorithmsSnapshot.json'
import { ALGORITHMS, type AlgoOption, type AlgorithmSpec } from './printRegistry'

// Drift test: the hand-maintained ``ALGORITHMS`` map in printRegistry.ts
// is checked against ``algorithmsSnapshot.json`` (regenerated from the
// backend's ``options_schema`` ClassVars via
// ``backend/scripts/regen_algorithms_snapshot.py``). If this fails:
//
//   1. Run ``uv run python scripts/regen_algorithms_snapshot.py`` in
//      ``backend/`` to refresh the fixture from the backend SoT.
//   2. Edit ``printRegistry.ts`` so each entry's ``defaults`` and
//      ``schema`` matches the new snapshot.
//
// The matching backend test
// (``test_algorithms_options_snapshot.py``) covers the other direction
// so the snapshot can't drift away from the backend either.

interface SnapshotOption {
  key: string
  label: string
  type: 'number' | 'integer' | 'boolean' | 'select'
  default: unknown
  min: number | null
  max: number | null
  step: number | null
  choices: string[] | null
}

interface SnapshotAlgorithm {
  name: string
  kind: 'fill' | 'lines' | 'mono_stroke'
  complexity: 'low' | 'medium' | 'high'
  options: SnapshotOption[]
}

const SNAPSHOT = snapshot as SnapshotAlgorithm[]

// ``noUncheckedIndexedAccess`` makes Record lookups ``| undefined``;
// centralise the existence check so the per-algorithm tests below can
// dereference the spec without per-line guards.
function getSpec(name: string): AlgorithmSpec {
  const spec = (ALGORITHMS as Record<string, AlgorithmSpec>)[name]
  if (!spec) throw new Error(`algorithm "${name}" missing from ALGORITHMS`)
  return spec
}

function frontendOption(opt: AlgoOption): SnapshotOption {
  // Normalise ``undefined`` to ``null`` so the comparison matches the
  // JSON snapshot's representation of "unset" fields.
  return {
    key: opt.key,
    label: opt.label,
    type: opt.type,
    default: undefined, // filled in from defaults map by caller
    min: opt.min ?? null,
    max: opt.max ?? null,
    step: opt.step ?? null,
    choices: opt.choices ?? null,
  }
}

describe('algorithmsSnapshot parity (backend SoT ↔ frontend ALGORITHMS)', () => {
  it('every snapshot algorithm exists in ALGORITHMS', () => {
    for (const entry of SNAPSHOT) {
      const spec = (ALGORITHMS as Record<string, AlgorithmSpec>)[entry.name]
      expect(spec, `algorithm "${entry.name}" missing from ALGORITHMS`).toBeDefined()
    }
  })

  it('every ALGORITHMS entry is covered by the snapshot', () => {
    const snapshotNames = new Set(SNAPSHOT.map((e) => e.name))
    for (const id of Object.keys(ALGORITHMS)) {
      expect(snapshotNames, `extra algorithm "${id}" not in backend snapshot`).toContain(id)
    }
  })

  for (const entry of SNAPSHOT) {
    it(`"${entry.name}" — schema matches backend (keys / types / bounds / choices)`, () => {
      const spec = getSpec(entry.name)
      const expected = entry.options.map(({ default: _d, ...rest }) => rest)
      const actual = spec.schema
        .map((opt) => frontendOption(opt))
        .map(({ default: _d, ...rest }) => rest)
      expect(actual, `schema drift for ${entry.name}`).toEqual(expected)
    })

    it(`"${entry.name}" — defaults match backend`, () => {
      const spec = getSpec(entry.name)
      for (const opt of entry.options) {
        if (opt.default === null || opt.default === undefined) continue
        const got = spec.defaults[opt.key]
        expect(
          got,
          `default mismatch ${entry.name}.${opt.key}: frontend=${JSON.stringify(got)} backend=${JSON.stringify(opt.default)}`,
        ).toEqual(opt.default)
      }
    })
  }
})
