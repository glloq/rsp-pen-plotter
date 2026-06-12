<script setup lang="ts">
// "Préparer le magasin" step (operator feedback): instead of bending
// the file's colours onto whatever pens happen to be mounted, compute
// the ink-loading plan FROM the file's wanted inks (assigned from the
// available-colours inventory) and ask the operator to load those into
// the magazine. When the file uses more inks than the magazine has
// slots, the plan schedules mid-print swaps — the backend pauses at
// each one (``slot_reinked`` in core/pause_logic) with a prompt naming
// the ink to load, so the whole inventory is usable on any machine.
//
// "Appliquer ce plan" commits three things at once:
//   1. each layer's ``target_pen_slot`` per the plan (and pins the
//      current ink as a manual assignment so a later pool change
//      can't silently reshuffle the plan),
//   2. the machine profile's pen slots (colour + name + installed)
//      so prompts, preflight and the 409 missing-slot check all agree
//      with what the operator is about to mount,
//   3. nothing else — pauses come from the backend's re-ink detection,
//      no per-layer pause_before fiddling needed.

import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MachineProfile, PenSlot } from '../../api/client'
import { buildInkLoadingPlan } from '../../lib/inkPlan'
import { canonicalHex } from '../../lib/penWidth'
import { useAvailableColorsStore } from '../../stores/availableColors'
import { useJobStore } from '../../stores/job'
import { useToastStore } from '../../stores/toasts'

const { t } = useI18n()
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

// Multi-pen machines only: mono machines already cycle any number of
// inks through their single holder via the colour-change pauses.
const visible = computed<boolean>(
  () => store.isMultiColor && slotCount.value >= 2 && store.layers.length > 0,
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

// True when the mounted magazine already matches the plan's initial
// loading — the operator applied the plan (or mounted by hand) and
// only the mid-print swaps remain.
const magazineReady = computed<boolean>(() => {
  const pens = store.selectedProfile?.pens ?? []
  return plan.value.initial.every((load) => {
    const pen = pens.find((p) => p.index === load.slot)
    return Boolean(pen?.installed && pen.color && canonicalHex(pen.color) === load.hex)
  })
})

// "Pick from the available colours": re-derive every auto layer's ink
// from the INVENTORY pool (distinct greedy ΔE matching) instead of the
// mounted pens. This is the step that frees the file from "whatever
// happens to be in the magazine" — the plan below then tells the
// operator what to mount. Manual overrides are preserved.
const inventoryPool = computed<string[]>(() => availableColors.ordered.map((c) => c.hex))
function pickFromInventory(): void {
  if (!inventoryPool.value.length) return
  store.resnapAutoLayers(inventoryPool.value)
}

const applying = ref(false)

async function applyPlan(): Promise<void> {
  const profile = store.selectedProfile
  if (!profile || applying.value) return
  applying.value = true
  try {
    // 1. Pin each layer to its planned slot + ink. Manual assignment so
    //    the palette-source resnap watcher can't reshuffle the plan.
    for (const l of planLayers.value) {
      const slot = plan.value.slotByLayer[l.layerId]
      if (slot === undefined) continue
      const named = inventoryNameByHex.value.get(l.hex.toLowerCase()) ?? null
      store.updateLayer(l.layerId, {
        target_pen_slot: slot,
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
    for (const load of plan.value.initial) {
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
    toasts.success(t('magazinePlan.applied'))
  } catch (err) {
    toasts.error((err as Error).message || t('magazinePlan.applyFailed'))
  } finally {
    applying.value = false
  }
}
</script>

<template>
  <section
    v-if="visible"
    class="space-y-2 rounded border border-slate-700 bg-slate-900/40 p-2.5 text-xs"
    data-test="magazine-plan"
  >
    <div class="flex items-baseline justify-between gap-2">
      <p class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
        {{ t('magazinePlan.title') }}
      </p>
      <span class="text-[10px] text-slate-500">
        {{ t('magazinePlan.summary', { inks: plan.inkCount, slots: slotCount }) }}
      </span>
    </div>

    <!-- Initial loading: what to mount before the print starts. -->
    <div class="space-y-1">
      <p class="text-[10px] text-slate-500">{{ t('magazinePlan.initialTitle') }}</p>
      <ul class="flex flex-wrap gap-1.5">
        <li
          v-for="load in plan.initial"
          :key="load.slot"
          class="inline-flex items-center gap-1.5 rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5"
          :data-test="`magazine-plan-slot-${load.slot}`"
        >
          <span class="font-mono text-[10px] text-slate-400">#{{ load.slot }}</span>
          <span
            class="inline-block h-3.5 w-3.5 rounded border border-slate-600"
            :style="{ backgroundColor: load.hex }"
            aria-hidden="true"
          />
          <span class="text-[11px] text-slate-200">{{ nameFor(load.hex) }}</span>
        </li>
      </ul>
    </div>

    <!-- Mid-print swaps: only when the file uses more inks than slots. -->
    <div v-if="plan.swaps.length" class="space-y-1" data-test="magazine-plan-swaps">
      <p class="text-[10px] text-slate-500">
        {{ t('magazinePlan.swapsTitle', { count: plan.swaps.length }) }}
      </p>
      <ol class="space-y-0.5">
        <li
          v-for="(swap, i) in plan.swaps"
          :key="`${swap.layerId}-${i}`"
          class="flex items-center gap-1.5 text-[11px] text-slate-300"
        >
          <span class="font-mono text-[10px] text-slate-500">{{ i + 1 }}.</span>
          <span class="font-mono text-[10px] text-slate-400">#{{ swap.slot }}</span>
          <span
            class="inline-block h-3 w-3 rounded border border-slate-600"
            :style="{ backgroundColor: swap.replacesHex }"
            aria-hidden="true"
          />
          <span aria-hidden="true" class="text-slate-500">→</span>
          <span
            class="inline-block h-3 w-3 rounded border border-slate-600"
            :style="{ backgroundColor: swap.hex }"
            aria-hidden="true"
          />
          <span>{{ nameFor(swap.hex) }}</span>
        </li>
      </ol>
      <p class="text-[10px] text-slate-500">{{ t('magazinePlan.pauseNote') }}</p>
      <p
        v-if="swapsUnsupported"
        class="rounded border border-amber-700 bg-amber-950/40 px-2 py-1 text-[10px] text-amber-200"
      >
        {{ t('magazinePlan.noPauseSupport') }}
      </p>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <button
        v-if="inventoryPool.length"
        type="button"
        class="rounded border border-slate-700 bg-slate-900 px-2.5 py-1 text-[11px] text-slate-300 hover:bg-slate-800"
        :title="t('magazinePlan.fromInventoryHint')"
        data-test="magazine-plan-from-inventory"
        @click="pickFromInventory"
      >
        ✦ {{ t('magazinePlan.fromInventory') }}
      </button>
      <button
        type="button"
        class="rounded border border-emerald-700 bg-emerald-950/40 px-2.5 py-1 text-[11px] text-emerald-200 hover:bg-emerald-950 disabled:opacity-40"
        :disabled="applying"
        data-test="magazine-plan-apply"
        @click="applyPlan"
      >
        {{ applying ? t('magazinePlan.applying') : t('magazinePlan.apply') }}
      </button>
      <span v-if="magazineReady" class="text-[10px] text-emerald-300" data-test="magazine-plan-ready">
        ✓ {{ t('magazinePlan.ready') }}
      </span>
    </div>
  </section>
</template>
