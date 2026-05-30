<script setup lang="ts">
// Colour-management fieldset for ProfileEditor.
//
// This is the operator-facing "how does this plotter handle colour?"
// switch. It deliberately does NOT manage individual pens / slot colours
// — that lives in the Couleurs tab. Here we only pick the colour mode
// and, when a magazine is involved, how many pens it holds:
//
//   - mono     → single pen, no tool change (tool_change_method = none)
//   - manual   → operator swaps pens by hand   (manual_pause)
//   - magazine → automatic carousel / rack     (carousel)
//
// Receives the draft profile via v-model so the parent stays the single
// owner of editable state; Vue allows mutating nested fields through a
// prop without tripping ``vue/no-mutating-props``. The mechanical pen
// commands (up / down / tool-change G-code) stay here too, tucked into a
// collapsible block, because they're machine config rather than colour
// inventory.

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MachineProfile, ToolChangeMethod } from '../api/client'

const { t } = useI18n()

const props = defineProps<{
  draft: MachineProfile
}>()

// Hard ceiling on configurable slots: a typo like "999" would render
// that many magazine rows and lock up the browser. No real plotter
// carousel exceeds this.
const MAX_PEN_SLOTS = 64

type ColorMode = 'mono' | 'manual' | 'magazine'

const colorMode = computed<ColorMode>(() => {
  switch (props.draft.tool_change_method) {
    case 'none':
      return 'mono'
    case 'manual_pause':
      return 'manual'
    default:
      // carousel / rack both present as an automatic magazine.
      return 'magazine'
  }
})

const modes: Array<{ id: ColorMode; method: ToolChangeMethod; icon: string }> = [
  { id: 'mono', method: 'none', icon: '✏️' },
  { id: 'manual', method: 'manual_pause', icon: '✋' },
  { id: 'magazine', method: 'carousel', icon: '🎡' },
]

function clampPenCount(): void {
  const n = Math.floor(props.draft.pen_slot_count)
  props.draft.pen_slot_count = Math.min(MAX_PEN_SLOTS, Math.max(2, Number.isFinite(n) ? n : 2))
}

function setMode(mode: ColorMode): void {
  const target = modes.find((m) => m.id === mode)
  if (!target) return
  props.draft.tool_change_method = target.method
  if (mode === 'mono') {
    // A single-pen plotter only ever has one slot.
    props.draft.pen_slot_count = 1
  } else if (props.draft.pen_slot_count < 2) {
    // Multicolour needs at least two pens — seed a sensible default the
    // operator can adjust right away.
    props.draft.pen_slot_count = 2
  }
}
</script>

<template>
  <details open class="group rounded-lg border border-slate-700 bg-slate-800/40">
    <summary
      class="flex cursor-pointer items-center justify-between px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200"
    >
      <span>④ {{ t('profile.colorManagement') }}</span>
      <span class="text-[10px] text-slate-500 group-open:hidden">
        {{ t(`profile.colorMode.${colorMode}`) }}
      </span>
    </summary>
    <div class="space-y-4 border-t border-slate-700 p-3">
      <p class="text-[11px] text-slate-500">{{ t('profile.colorManagementHint') }}</p>

      <!-- Mode selector: three big, obvious cards -->
      <div class="grid grid-cols-1 gap-2 sm:grid-cols-3" data-test="color-mode-selector">
        <button
          v-for="mode in modes"
          :key="mode.id"
          type="button"
          class="flex flex-col gap-1 rounded-lg border p-3 text-left transition"
          :class="
            colorMode === mode.id
              ? 'border-emerald-500 bg-emerald-950/40 ring-1 ring-emerald-500'
              : 'border-slate-700 bg-slate-900/60 hover:border-slate-500'
          "
          :aria-pressed="colorMode === mode.id"
          :data-test="`color-mode-${mode.id}`"
          @click="setMode(mode.id)"
        >
          <span class="flex items-center gap-2">
            <span class="text-lg leading-none">{{ mode.icon }}</span>
            <span
              class="text-sm font-medium"
              :class="colorMode === mode.id ? 'text-emerald-200' : 'text-slate-200'"
            >
              {{ t(`profile.colorMode.${mode.id}`) }}
            </span>
          </span>
          <span class="text-[11px] leading-snug text-slate-400">
            {{ t(`profile.colorModeHint.${mode.id}`) }}
          </span>
        </button>
      </div>

      <!-- Pen count — only meaningful for multicolour plotters. -->
      <div
        v-if="colorMode !== 'mono'"
        class="rounded-lg border border-slate-700 bg-slate-900/50 p-3"
        data-test="magazine-pen-count"
      >
        <label class="block text-slate-400">
          {{ t('profile.penCount') }}
          <input
            v-model.number="draft.pen_slot_count"
            type="number"
            min="2"
            :max="MAX_PEN_SLOTS"
            class="mt-1 w-28 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
            @change="clampPenCount"
          />
        </label>
        <p class="mt-1 text-[11px] text-slate-500">
          {{
            colorMode === 'magazine'
              ? t('profile.penCountMagazineHint')
              : t('profile.penCountManualHint')
          }}
        </p>
      </div>
      <p v-else class="text-[11px] text-slate-500">{{ t('profile.monoNote') }}</p>

      <!-- Tool-change command — only the magazine mode triggers it. The
           mechanical pen up/down commands moved to the Motion section
           (they're shared machine config, not magazine-specific). -->
      <label v-if="colorMode === 'magazine'" class="block text-slate-400">
        {{ t('profile.toolChangeCommand') }}
        <input
          v-model="draft.tool_change_command"
          type="text"
          class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100"
        />
      </label>
    </div>
  </details>
</template>
