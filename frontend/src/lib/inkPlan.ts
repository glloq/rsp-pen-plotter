// Ink-loading plan: which colours go into which magazine slots, and
// which mid-print swaps are needed when the file uses MORE colours
// than the magazine has slots.
//
// The plan is computed from the layers' effective inks in draw order
// (assigned hex when set, source colour otherwise). Slot eviction is
// Belady's algorithm — when every slot is busy, replace the ink whose
// next use is farthest in the future (or never) — which minimises the
// number of operator swaps for the given draw order.
//
// Pure function so it has unit tests independent of Vue/Pinia. The
// backend counterpart is the per-slot ink tracking in
// ``core/pause_logic.initial_slot_inks`` + the ``slot_reinked`` pause:
// applying this plan (slots written to ``target_pen_slot``) makes the
// generated G-code pause exactly at each ``swaps`` entry with a
// prompt naming the ink to load.

import { canonicalHex } from './penWidth'

export interface InkPlanLayer {
  layerId: string
  /** Effective ink for the layer (assigned hex, else source colour). */
  hex: string
}

export interface SlotLoad {
  slot: number
  hex: string
}

export interface InkSwap {
  /** Layer right before which the operator swaps the slot's pen. */
  layerId: string
  slot: number
  /** Ink to load into the slot. */
  hex: string
  /** Ink the swap removes from the slot. */
  replacesHex: string
}

export interface InkLoadingPlan {
  /** Pens to mount BEFORE the print starts, in slot order of first use. */
  initial: SlotLoad[]
  /** Mid-print pen swaps, in draw order. Empty when inks ≤ slots. */
  swaps: InkSwap[]
  /** Magazine slot each layer draws from. */
  slotByLayer: Record<string, number>
  /** Distinct ink count across the plan. */
  inkCount: number
}

export function buildInkLoadingPlan(
  layers: readonly InkPlanLayer[],
  slotCount: number,
): InkLoadingPlan {
  const seq = layers.map((l) => ({ layerId: l.layerId, hex: canonicalHex(l.hex) }))
  const plan: InkLoadingPlan = {
    initial: [],
    swaps: [],
    slotByLayer: {},
    inkCount: new Set(seq.map((l) => l.hex)).size,
  }
  if (slotCount <= 0 || seq.length === 0) return plan

  const slotInk: (string | null)[] = Array.from({ length: slotCount }, () => null)

  // Index of the next layer (strictly after ``after``) drawing ``hex``;
  // Infinity when the ink never comes back. Drives the Belady eviction.
  function nextUse(hex: string, after: number): number {
    for (let j = after + 1; j < seq.length; j++) {
      if (seq[j]!.hex === hex) return j
    }
    return Infinity
  }

  seq.forEach((layer, i) => {
    let slot = slotInk.indexOf(layer.hex)
    if (slot === -1) {
      const free = slotInk.indexOf(null)
      if (free !== -1) {
        slot = free
        plan.initial.push({ slot, hex: layer.hex })
      } else {
        // Every slot is busy: evict the ink whose next use is farthest.
        let evict = 0
        let farthest = -1
        for (let s = 0; s < slotCount; s++) {
          const n = nextUse(slotInk[s]!, i)
          if (n > farthest) {
            farthest = n
            evict = s
          }
        }
        plan.swaps.push({
          layerId: layer.layerId,
          slot: evict,
          hex: layer.hex,
          replacesHex: slotInk[evict]!,
        })
        slot = evict
      }
      slotInk[slot] = layer.hex
    }
    plan.slotByLayer[layer.layerId] = slot
  })
  return plan
}
