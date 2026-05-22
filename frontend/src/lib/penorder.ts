import type { LayerInfo } from '../api/client'

function penKey(layer: LayerInfo): string {
  return layer.target_pen_slot === null ? 'none' : String(layer.target_pen_slot)
}

/**
 * Count pen changes a draw order incurs: each transition to a different
 * assigned slot (ignoring unassigned layers, which need no tool change).
 */
export function countPenChanges(layers: LayerInfo[]): number {
  let changes = 0
  let previous: number | null = null
  for (const layer of layers) {
    const slot = layer.target_pen_slot
    if (slot === null || slot === previous) continue
    changes += 1
    previous = slot
  }
  return changes
}

/**
 * Reorder layers to group those sharing a pen slot, minimizing tool changes.
 *
 * Groups are emitted in first-appearance order and layers keep their relative
 * order within a group, so the result is a stable rearrangement the user can
 * still tweak by dragging.
 */
export function groupByPen(layers: LayerInfo[]): LayerInfo[] {
  const groups = new Map<string, LayerInfo[]>()
  for (const layer of layers) {
    const key = penKey(layer)
    const group = groups.get(key)
    if (group) group.push(layer)
    else groups.set(key, [layer])
  }
  return [...groups.values()].flat()
}

/** Whether grouping by pen would reduce the number of tool changes. */
export function canReduceSwaps(layers: LayerInfo[]): boolean {
  return countPenChanges(groupByPen(layers)) < countPenChanges(layers)
}
