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
// All the plan/apply logic lives in ``useMagazinePlan`` (shared with
// the print-launch MagazineLoadModal); this panel is the passive
// planning surface inside the Layers tab.

import { useI18n } from 'vue-i18n'
import { useMagazinePlan } from '../../composables/useMagazinePlan'
import { useToastStore } from '../../stores/toasts'

const { t } = useI18n()
const toasts = useToastStore()

const {
  slotCount,
  plan,
  needed,
  swapsUnsupported,
  nameFor,
  magazineReady,
  inventoryPool,
  pickFromInventory,
  applying,
  applyPlan,
} = useMagazinePlan()

async function onApply(): Promise<void> {
  const outcome = await applyPlan()
  if (outcome === 'applied' || outcome === 'unchanged') {
    toasts.success(t('magazinePlan.applied'))
  }
}
</script>

<template>
  <section
    v-if="needed"
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
        @click="onApply"
      >
        {{ applying ? t('magazinePlan.applying') : t('magazinePlan.apply') }}
      </button>
      <span v-if="magazineReady" class="text-[10px] text-emerald-300" data-test="magazine-plan-ready">
        ✓ {{ t('magazinePlan.ready') }}
      </span>
    </div>
  </section>
</template>
