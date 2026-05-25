<script setup lang="ts">
// LayerCard sub-component: per-layer colour picker driven by the
// active palette pool (installed pens / available colours / union).
//
// Shows the layer's current assigned hex with a swatch + label, then
// lets the operator swap it out by picking from the effective palette
// via a swatch strip. The "↻ auto" button re-runs the nearest-match
// (CIE Lab ΔE 2000) frontend-side so the operator sees the snap
// instantly without an /upload round-trip.
//
// Wiring lives in the parent LayerCard — this component only reads
// the layer prop, the effective palette and the inventory store
// (for hex → human-name lookup), and emits one event per intent.

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ColorAssignment, LayerInfo } from '../../api/client'
import { nearestPoolHex } from '../../lib/nearestColor'
import { useAvailableColorsStore } from '../../stores/availableColors'

const { t } = useI18n()
const availableColorsStore = useAvailableColorsStore()

const props = defineProps<{
  layer: LayerInfo
  /** Active palette pool resolved from the source toggle + pens + inventory. */
  effectivePalette: readonly string[]
}>()

const emit = defineEmits<{
  /** Pick a specific colour. Caller persists assigned_color_hex + flag. */
  pick: [{ hex: string; assignment: ColorAssignment }]
  /** Reset to auto: caller computes the nearest match and persists. */
  reset: [{ hex: string | null }]
}>()

// Display label for a hex: prefer the operator's inventory name, fall
// back to the canonical hex form. Lookup is case-insensitive because
// the inventory canonicalises to lowercase but the layer's
// ``assigned_color_hex`` may come in upper-case from older snapshots.
const inventoryByHex = computed(() => {
  const map = new Map<string, string>()
  for (const entry of availableColorsStore.colors) {
    map.set(entry.hex.toLowerCase(), entry.name)
  }
  return map
})

function labelFor(hex: string): string {
  const name = inventoryByHex.value.get(hex.toLowerCase())
  return name && name.trim() ? name : hex
}

const currentHex = computed<string | null>(() => props.layer.assigned_color_hex)
const isManual = computed(() => props.layer.color_assignment === 'manual')

function onPick(hex: string): void {
  emit('pick', { hex, assignment: 'manual' })
}

function onResetAuto(): void {
  // Compute the auto pick locally so the LayerCard updates before
  // the next /upload reseeds it. ``null`` is a valid result when the
  // pool is empty — the G-code path falls back to source_color.
  const nearest = nearestPoolHex(props.layer.source_color, props.effectivePalette)
  emit('reset', { hex: nearest })
}
</script>

<template>
  <div class="space-y-1.5 rounded border border-slate-800 bg-slate-900/40 p-2">
    <div class="flex items-baseline justify-between">
      <p class="text-[10px] uppercase tracking-wider text-slate-500">
        {{ t('assignedColor.title') }}
      </p>
      <button
        v-if="isManual"
        type="button"
        class="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[10px] text-slate-300 hover:border-emerald-600 hover:text-emerald-200"
        :title="t('assignedColor.resetTitle')"
        @click="onResetAuto"
      >
        ↻ {{ t('assignedColor.reset') }}
      </button>
    </div>

    <!-- Current assignment line -->
    <div class="flex items-center gap-2">
      <span
        class="inline-block h-5 w-5 shrink-0 rounded border border-slate-600"
        :style="{ backgroundColor: currentHex ?? layer.source_color }"
        :aria-label="currentHex ?? layer.source_color"
      />
      <span class="flex-1 truncate text-xs text-slate-200">
        {{ currentHex ? labelFor(currentHex) : layer.source_color }}
      </span>
      <span
        class="rounded px-1 py-0.5 text-[10px] font-mono"
        :class="
          isManual
            ? 'border border-amber-700 bg-amber-950/40 text-amber-200'
            : 'border border-slate-700 bg-slate-900 text-slate-400'
        "
      >
        {{ isManual ? t('assignedColor.manual') : t('assignedColor.auto') }}
      </span>
    </div>

    <!-- Picker: clickable swatches from the effective palette. -->
    <div v-if="effectivePalette.length" class="space-y-1">
      <p class="text-[10px] text-slate-500">{{ t('assignedColor.pickHint') }}</p>
      <div class="flex flex-wrap gap-1">
        <button
          v-for="hex in effectivePalette"
          :key="hex"
          type="button"
          class="inline-flex h-5 w-5 cursor-pointer items-center justify-center rounded border transition"
          :class="
            currentHex && currentHex.toLowerCase() === hex.toLowerCase()
              ? 'border-emerald-400 ring-1 ring-emerald-500'
              : 'border-slate-600 hover:border-slate-400'
          "
          :style="{ backgroundColor: hex }"
          :title="labelFor(hex)"
          :aria-label="labelFor(hex)"
          @click="onPick(hex)"
        />
      </div>
    </div>
    <p v-else class="text-[10px] text-slate-500">
      {{ t('assignedColor.emptyPool') }}
    </p>
  </div>
</template>
