// Shared magazine-plan logic: which inks the SELECTED placement needs,
// how they map onto magazine slots (Belady plan from lib/inkPlan), and
// the "apply" mutation that pins layer slots + declares the loading in
// the machine profile.
//
// Two consumers:
//   - MagazinePlanPanel (Layers tab) — passive planning surface
//   - MagazineLoadModal (print launch) — blocking confirmation that
//     also lets the operator REMAP which slot carries which ink
//
// The remap is expressed as a permutation ``planSlot → physicalSlot``:
// the Belady plan's slot indices are just labels, so applying a
// bijection to every slot reference (initial loads, swaps, per-layer
// slots) keeps the plan optimal while honouring the operator's
// preferred physical arrangement.
//
// NOTE: the plan covers the SELECTED placement (the editor's working
// set). Multi-placement plans would need a cross-placement plan — out
// of scope for v0.3.

import { computed, ref } from 'vue'
import type { MachineProfile, PenSlot } from '../api/client'
import { i18n } from '../i18n'
import { buildInkLoadingPlan, type InkSwap, type SlotLoad } from '../lib/inkPlan'
import { canonicalHex } from '../lib/penWidth'
import { useAvailableColorsStore } from '../stores/availableColors'
import { useJobStore } from '../stores/job'
import { useToastStore } from '../stores/toasts'

/** planSlot → physical slot. Identity when omitted. */
export type SlotPermutation = Record<number, number>

export type ApplyOutcome = 'unchanged' | 'applied' | 'failed'

export function useMagazinePlan() {
  const store = useJobStore()
  const availableColors = useAvailableColorsStore()
  const toasts = useToastStore()

  const slotCount = computed<number>(() => store.selectedProfile?.pen_slot_count ?? 0)

  // Layers in draw order with their effective ink — the same colour the
  // G-code will draw with (assigned hex wins over the raw centroid).
  const planLayers = computed(() =>
    [...store.layers]
      .sort((a, b) => a.draw_order - b.draw_order)
      .map((l) => ({ layerId: l.layer_id, hex: l.assigned_color_hex ?? l.source_color })),
  )

  const plan = computed(() => buildInkLoadingPlan(planLayers.value, slotCount.value))

  // Every machine with a holder and at least two inks needs a loading
  // plan now — including single-holder machines, where the plan is one
  // initial pen plus a manual swap at each colour change. (Previously
  // restricted to multi-slot magazines, which silently dropped the
  // single-holder swap prompts.)
  const needed = computed<boolean>(
    () => slotCount.value >= 1 && plan.value.inkCount >= 2 && store.layers.length > 0,
  )

  // Profiles that declare no tool-change support can't pause mid-print —
  // a plan with swaps would silently draw wrong colours.
  const swapsUnsupported = computed<boolean>(
    () => plan.value.swaps.length > 0 && store.selectedProfile?.tool_change_method === 'none',
  )

  const inventoryNameByHex = computed(() => {
    const map = new Map<string, string>()
    for (const entry of availableColors.colors) {
      if (entry.name && entry.name.trim()) map.set(entry.hex.toLowerCase(), entry.name)
    }
    return map
  })
  function nameFor(hex: string): string {
    return inventoryNameByHex.value.get(hex.toLowerCase()) ?? hex
  }

  function mapSlot(slot: number, permutation?: SlotPermutation): number {
    return permutation?.[slot] ?? slot
  }
  function remappedInitial(permutation?: SlotPermutation): SlotLoad[] {
    return plan.value.initial.map((l) => ({ ...l, slot: mapSlot(l.slot, permutation) }))
  }
  function remappedSwaps(permutation?: SlotPermutation): InkSwap[] {
    return plan.value.swaps.map((s) => ({ ...s, slot: mapSlot(s.slot, permutation) }))
  }

  // True when the mounted magazine already matches the plan's initial
  // loading — the operator applied the plan (or mounted by hand) and
  // only the mid-print swaps remain.
  function magazineMatches(permutation?: SlotPermutation): boolean {
    const pens = store.selectedProfile?.pens ?? []
    return remappedInitial(permutation).every((load) => {
      const pen = pens.find((p) => p.index === load.slot)
      return Boolean(pen?.installed && pen.color && canonicalHex(pen.color) === load.hex)
    })
  }
  const magazineReady = computed<boolean>(() => magazineMatches())

  // True when applying the plan would be a no-op: every layer already
  // pinned to its planned slot+ink and the profile pens already match.
  function planApplied(permutation?: SlotPermutation): boolean {
    if (!magazineMatches(permutation)) return false
    const byId = new Map(store.layers.map((l) => [l.layer_id, l]))
    return planLayers.value.every((pl) => {
      const layer = byId.get(pl.layerId)
      const want = plan.value.slotByLayer[pl.layerId]
      if (!layer || want === undefined) return false
      return (
        layer.target_pen_slot === mapSlot(want, permutation) &&
        layer.color_assignment === 'manual' &&
        canonicalHex(layer.assigned_color_hex ?? layer.source_color) === canonicalHex(pl.hex)
      )
    })
  }

  // "Pick from the available colours": re-derive every auto layer's ink
  // from the INVENTORY pool (distinct greedy ΔE matching) instead of the
  // mounted pens. Manual overrides are preserved.
  const inventoryPool = computed<string[]>(() => availableColors.ordered.map((c) => c.hex))
  function pickFromInventory(): void {
    if (!inventoryPool.value.length) return
    store.resnapAutoLayers(inventoryPool.value)
  }

  const applying = ref(false)

  async function applyPlan(permutation?: SlotPermutation): Promise<ApplyOutcome> {
    const profile = store.selectedProfile
    if (!profile || applying.value) return 'failed'
    if (planApplied(permutation)) return 'unchanged'
    applying.value = true
    try {
      // 1. Pin each layer to its planned slot + ink. Manual assignment
      //    so the palette-source resnap watcher can't reshuffle the plan.
      for (const l of planLayers.value) {
        const slot = plan.value.slotByLayer[l.layerId]
        if (slot === undefined) continue
        const named = inventoryNameByHex.value.get(l.hex.toLowerCase()) ?? null
        store.updateLayer(l.layerId, {
          target_pen_slot: mapSlot(slot, permutation),
          assigned_color_hex: canonicalHex(l.hex),
          color_assignment: 'manual',
          // Inventory name feeds the swap prompts ("Insert pen slot 2:
          // Vert prairie") — leave whatever label exists otherwise.
          ...(named ? { color_label: named } : {}),
        })
      }

      // 2. Declare the initial loading in the machine profile so the
      //    prompts / preflight / missing-slot check agree with the pens
      //    the operator is being asked to mount.
      const pensByIndex = new Map<number, PenSlot>((profile.pens ?? []).map((p) => [p.index, p]))
      for (const load of remappedInitial(permutation)) {
        const existing = pensByIndex.get(load.slot)
        pensByIndex.set(load.slot, {
          index: load.slot,
          name: nameFor(load.hex),
          color: load.hex,
          installed: true,
          position: existing?.position ?? null,
          pen_up_command: existing?.pen_up_command ?? null,
          pen_down_command: existing?.pen_down_command ?? null,
        })
      }
      const next: MachineProfile = {
        ...profile,
        pens: [...pensByIndex.values()].sort((a, b) => a.index - b.index),
      }
      await store.saveProfile(next)
      return 'applied'
    } catch (err) {
      toasts.error((err as Error).message || i18n.global.t('magazinePlan.applyFailed'))
      return 'failed'
    } finally {
      applying.value = false
    }
  }

  return {
    slotCount,
    planLayers,
    plan,
    needed,
    swapsUnsupported,
    nameFor,
    remappedInitial,
    remappedSwaps,
    magazineReady,
    planApplied,
    inventoryPool,
    pickFromInventory,
    applying,
    applyPlan,
  }
}
