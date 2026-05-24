// @deprecated — façade. The schemas live in ``./printRegistry.ts``
// now. New code should import ``ALGORITHMS``, ``getAlgorithm``, or
// ``defaultsFor`` from there directly. This file keeps the old names
// alive so the migration can happen one consumer at a time.

import {
  ALGORITHMS,
  getAlgorithm,
  defaultsFor as defaultsForReg,
  type AlgoOption,
  type AlgorithmSpec,
} from './printRegistry'

export type { AlgoOption }
// Old type alias — kept so existing imports of ``AlgoSpec`` resolve.
export type AlgoSpec = AlgorithmSpec

// Old shape was ``Record<string, AlgoSpec>``; the registry exports the
// strictly-typed ``Record<AlgorithmId, AlgorithmSpec>``. Cast back to
// the loose shape so legacy code that indexes with ``string`` works.
export const ALGO_OPTIONS: Record<string, AlgoSpec> = ALGORITHMS

export function getAlgoSpec(name: string | null | undefined): AlgoSpec | null {
  return getAlgorithm(name)
}

export function defaultsFor(name: string): Record<string, unknown> {
  return defaultsForReg(name)
}
