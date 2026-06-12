<script setup lang="ts">
// Print-launch magazine modal — blocks the "send to plotter" action
// until the operator confirms the needed inks are loaded in the
// magazine slots. Each ink row carries a slot <select> so the operator
// can declare which physical slot holds which colour (the Belady
// plan's slot indices are labels; remapping is a permutation applied
// to every slot reference, so the swap schedule stays optimal).
//
// Confirming applies the plan (per-layer slots + profile pens) and —
// because any layer mutation invalidates the generated G-code —
// re-runs the generate pipeline before resolving, so the launch site
// always sends a program that matches what the operator just mounted.
//
// Mounted once in App.vue; driven by the ``magazineGate`` singleton.

import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  resolveMagazineGate,
  useMagazineGateState,
} from '../composables/magazineGate'
import { useMagazinePlan, type SlotPermutation } from '../composables/useMagazinePlan'
import { useJobStore } from '../stores/job'
import { useToastStore } from '../stores/toasts'

const { t } = useI18n()
const gate = useMagazineGateState()
const job = useJobStore()
const toasts = useToastStore()

const {
  slotCount,
  plan,
  swapsUnsupported,
  nameFor,
  remappedSwaps,
  applying,
  applyPlan,
} = useMagazinePlan()

// planSlot → physical slot, editable through the selects. Reset to the
// identity every time the modal opens so a previous session's remap
// can't leak into a new print.
const slotChoice = reactive<Record<number, number>>({})
watch(
  () => gate.open,
  (open) => {
    if (!open) return
    for (const key of Object.keys(slotChoice)) delete slotChoice[Number(key)]
    for (const load of plan.value.initial) slotChoice[load.slot] = load.slot
  },
)

const permutation = computed<SlotPermutation>(() => ({ ...slotChoice }))

// Initial loads shown with the operator's chosen physical slot.
const initialRows = computed(() =>
  plan.value.initial.map((load) => ({
    planSlot: load.slot,
    physicalSlot: slotChoice[load.slot] ?? load.slot,
    hex: load.hex,
  })),
)

const slotOptions = computed<number[]>(() =>
  Array.from({ length: slotCount.value }, (_, i) => i),
)

// Keep the mapping a bijection: picking a slot already held by another
// ink swaps the two rows instead of silently double-booking the slot.
function onPickSlot(planSlot: number, raw: string): void {
  const target = Number(raw)
  if (!Number.isInteger(target)) return
  const current = slotChoice[planSlot] ?? planSlot
  if (target === current) return
  for (const [otherPlanSlot, phys] of Object.entries(slotChoice)) {
    if (Number(otherPlanSlot) !== planSlot && phys === target) {
      slotChoice[Number(otherPlanSlot)] = current
      break
    }
  }
  slotChoice[planSlot] = target
}

const displayedSwaps = computed(() => remappedSwaps(permutation.value))

const busy = ref(false)

async function confirm(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    const outcome = await applyPlan(permutation.value)
    if (outcome === 'failed') return // toast shown by applyPlan; stay open
    if (outcome === 'applied') {
      // The layer/profile mutations invalidated the generated G-code —
      // regenerate so the launch site sends a program that matches the
      // magazine the operator just confirmed.
      await job.generate()
      if (!job.gcode) {
        toasts.error(t('magazinePlan.launchRegenFailed'))
        resolveMagazineGate('cancelled')
        return
      }
    }
    resolveMagazineGate('confirmed')
  } finally {
    busy.value = false
  }
}

function cancel(): void {
  if (busy.value) return
  resolveMagazineGate('cancelled')
}
</script>

<template>
  <div
    v-if="gate.open"
    class="fixed inset-0 z-[10040] flex items-center justify-center bg-black/70 p-4"
    role="dialog"
    aria-modal="true"
    :aria-label="t('magazinePlan.launchTitle')"
    data-test="magazine-load-modal"
  >
    <div
      class="w-full max-w-lg space-y-4 rounded-xl border border-slate-600 bg-slate-900 p-6 shadow-2xl"
    >
      <header class="space-y-1 text-center">
        <div
          class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/20 text-2xl"
          aria-hidden="true"
        >
          🖊
        </div>
        <h2 class="text-lg font-semibold text-slate-100">{{ t('magazinePlan.launchTitle') }}</h2>
        <p class="text-xs text-slate-400">{{ t('magazinePlan.launchIntro') }}</p>
      </header>

      <!-- Initial loading with editable slot assignment. -->
      <ul class="space-y-1.5">
        <li
          v-for="row in initialRows"
          :key="row.planSlot"
          class="flex items-center gap-2 rounded border border-slate-700 bg-slate-800/60 px-2.5 py-1.5"
          :data-test="`magazine-load-row-${row.planSlot}`"
        >
          <label class="flex items-center gap-1.5 text-[11px] text-slate-400">
            <span>{{ t('magazinePlan.slotLabel') }}</span>
            <select
              :value="row.physicalSlot"
              class="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 font-mono text-[11px] text-slate-100"
              :aria-label="t('magazinePlan.slotPick', { name: nameFor(row.hex) })"
              :data-test="`magazine-load-slot-${row.planSlot}`"
              @change="onPickSlot(row.planSlot, ($event.target as HTMLSelectElement).value)"
            >
              <option v-for="s in slotOptions" :key="s" :value="s">{{ s }}</option>
            </select>
          </label>
          <span
            class="inline-block h-4 w-4 rounded border border-slate-600"
            :style="{ backgroundColor: row.hex }"
            aria-hidden="true"
          />
          <span class="min-w-0 flex-1 truncate text-sm text-slate-100">{{ nameFor(row.hex) }}</span>
          <span class="font-mono text-[10px] text-slate-500">{{ row.hex }}</span>
        </li>
      </ul>

      <!-- Mid-print swap schedule (when inks > slots). -->
      <div
        v-if="displayedSwaps.length"
        class="space-y-1 rounded border border-slate-700 bg-slate-800/40 px-2.5 py-2"
        data-test="magazine-load-swaps"
      >
        <p class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
          {{ t('magazinePlan.swapsTitle', { count: displayedSwaps.length }) }}
        </p>
        <ol class="space-y-0.5">
          <li
            v-for="(swap, i) in displayedSwaps"
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

      <footer class="flex flex-col gap-2">
        <button
          type="button"
          class="w-full rounded-lg bg-emerald-600 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
          :disabled="busy || applying"
          data-test="magazine-load-confirm"
          @click="confirm"
        >
          {{ busy ? t('magazinePlan.launchPreparing') : t('magazinePlan.launchConfirm') }}
        </button>
        <button
          type="button"
          class="w-full rounded-lg border border-slate-700 bg-transparent px-4 py-2 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
          :disabled="busy"
          data-test="magazine-load-cancel"
          @click="cancel"
        >
          {{ t('magazinePlan.launchCancel') }}
        </button>
      </footer>
    </div>
  </div>
</template>
