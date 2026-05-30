<script setup lang="ts">
// Tool-change fieldset for ProfileEditor.
//
// This is the operator-facing "how does this plotter change pens?"
// switch. It writes the v0.2 capability model (the runtime source of
// truth for *how* a swap executes) AND keeps the legacy
// ``tool_change_method`` field in sync (it still drives *where* the
// pauses are placed + back-compat YAML export). The two must never
// disagree, so every mode change goes through ``setMode``.
//
// Four modes, mapped to capability ToolingMode + legacy method:
//   - mono     → single_pen / none         (one pen, no swap)
//   - manual   → manual     / manual_pause (operator swaps by hand)
//   - firmware → firmware   / carousel     (plotter swaps on one G-code command)
//   - host     → host_macro / rack         (the Pi emits a G-code sequence)
//
// Per-pen colours / slots live in the Couleurs tab; this fieldset only
// owns the swap strategy + magazine size + the firmware trigger or the
// host macro sequence.
//
// Receives the draft profile via v-model so the parent stays the single
// owner of editable state; Vue allows mutating nested fields through a
// prop without tripping ``vue/no-mutating-props``.

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MachineProfile, ToolChangeMethod } from '../api/client'
import {
  defaultCapabilities,
  type CommandSource,
  type HostSwapPlan,
  type HostSwapStepKind,
  type MachineCapabilities,
  type ToolingMode,
} from '../domain/capability/schemas'

const { t } = useI18n()

const props = defineProps<{
  draft: MachineProfile
}>()

// Hard ceiling on configurable slots: a typo like "999" would render
// that many magazine rows and lock up the browser. No real plotter
// carousel exceeds this.
const MAX_PEN_SLOTS = 64

type ColorMode = 'mono' | 'manual' | 'firmware' | 'host'

interface ModeSpec {
  id: ColorMode
  method: ToolChangeMethod
  tooling: ToolingMode
  source: CommandSource
  icon: string
}

const modes: ModeSpec[] = [
  { id: 'mono', method: 'none', tooling: 'single_pen', source: 'machine', icon: '✏️' },
  { id: 'manual', method: 'manual_pause', tooling: 'manual', source: 'operator', icon: '✋' },
  { id: 'firmware', method: 'carousel', tooling: 'firmware', source: 'machine', icon: '🎡' },
  { id: 'host', method: 'rack', tooling: 'host_macro', source: 'host', icon: '🤖' },
]

// Capabilities is the source of truth for the mode; fall back to the
// legacy field for profiles untouched since migration.
const colorMode = computed<ColorMode>(() => {
  const tooling = props.draft.capabilities?.tool_change.mode
  const byTooling = modes.find((m) => m.tooling === tooling)
  if (byTooling) return byTooling.id
  switch (props.draft.tool_change_method) {
    case 'none':
      return 'mono'
    case 'manual_pause':
      return 'manual'
    case 'rack':
      return 'host'
    default:
      return 'firmware'
  }
})

// Ensure the draft carries an editable capabilities block, seeded from
// the current legacy mode when absent (a freshly-created profile).
function ensureCaps(): MachineCapabilities {
  if (!props.draft.capabilities) {
    const seed = modes.find((m) => m.method === props.draft.tool_change_method)
    props.draft.capabilities = defaultCapabilities(seed?.tooling ?? 'manual')
  }
  return props.draft.capabilities
}

// Read-only view of the macro list (no side effects in the getter).
// When host mode is active the capabilities block is guaranteed present
// (setMode / backend migration ensure it), so this never hits the
// fallback during the host editor render.
// Structured, G-code-free host swap. The operator orders high-level
// blocks; the backend compiles them using each pen's calibrated
// position (set in the magazine editor).
const STEP_KINDS: HostSwapStepKind[] = [
  'head_up',
  'head_down',
  'move_to_old_slot',
  'move_to_new_slot',
  'grab',
  'release',
  'dwell',
  'raw',
]

function defaultHostSwap(): HostSwapPlan {
  return {
    grab_command: 'M280 P1 S90',
    drop_command: 'M280 P1 S20',
    travel_speed_mm_s: null,
    steps: [
      { kind: 'head_up', wait_ms: 0, send: '' },
      { kind: 'move_to_old_slot', wait_ms: 0, send: '' },
      { kind: 'release', wait_ms: 200, send: '' },
      { kind: 'move_to_new_slot', wait_ms: 0, send: '' },
      { kind: 'grab', wait_ms: 200, send: '' },
      { kind: 'head_down', wait_ms: 0, send: '' },
    ],
  }
}

function ensureHostSwap(): HostSwapPlan {
  const tc = ensureCaps().tool_change
  if (!tc.host_swap) tc.host_swap = defaultHostSwap()
  return tc.host_swap
}

// Read-only view for the template (no side effects in the getter).
const hostSwap = computed(() => props.draft.capabilities?.tool_change.host_swap ?? null)

function addStep(): void {
  ensureHostSwap().steps.push({ kind: 'dwell', wait_ms: 200, send: '' })
}

function removeStep(index: number): void {
  ensureHostSwap().steps.splice(index, 1)
}

function moveStep(index: number, delta: number): void {
  const steps = ensureHostSwap().steps
  const next = index + delta
  if (next < 0 || next >= steps.length) return
  const [s] = steps.splice(index, 1)
  steps.splice(next, 0, s!)
}

function clampPenCount(): void {
  const n = Math.floor(props.draft.pen_slot_count)
  props.draft.pen_slot_count = Math.min(MAX_PEN_SLOTS, Math.max(2, Number.isFinite(n) ? n : 2))
  ensureCaps().max_pens_in_magazine = Math.max(1, props.draft.pen_slot_count)
}

function setMode(mode: ColorMode): void {
  const target = modes.find((m) => m.id === mode)
  if (!target) return
  const caps = ensureCaps()
  const tc = caps.tool_change

  // Keep legacy + capability in lockstep so pause placement (legacy)
  // and swap execution (capability) never disagree.
  props.draft.tool_change_method = target.method
  tc.mode = target.tooling
  tc.command_source = target.source

  if (mode === 'mono') {
    props.draft.pen_slot_count = 1
  } else if (props.draft.pen_slot_count < 2) {
    // Multicolour needs at least two pens — seed a sensible default.
    props.draft.pen_slot_count = 2
  }
  caps.max_pens_in_magazine = Math.max(1, props.draft.pen_slot_count)

  // Manual keeps an editable prompt; clear it otherwise.
  if (mode === 'manual' && !tc.manual_prompt) {
    tc.manual_prompt = {
      title: 'Change pen',
      body: 'Insert pen {color} into the holder, then press Resume.',
      timeout_s: null,
    }
  } else if (mode !== 'manual') {
    tc.manual_prompt = null
  }

  // Firmware uses the single ``tool_change_command`` trigger. Host uses
  // the structured visual builder (``host_swap``); the raw ``host_macro``
  // list stays empty so the builder is the single source of truth.
  if (mode === 'host') {
    if (!tc.host_swap) tc.host_swap = defaultHostSwap()
  } else {
    tc.host_swap = null
  }
  tc.host_macro = []
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

      <!-- Mode selector: four cards. Firmware vs Host make the two
           magazine cases explicit (plotter-driven single command vs
           Pi-driven G-code sequence). -->
      <div class="grid grid-cols-2 gap-2 sm:grid-cols-4" data-test="color-mode-selector">
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
            colorMode === 'manual'
              ? t('profile.penCountManualHint')
              : t('profile.penCountMagazineHint')
          }}
        </p>
      </div>
      <p v-else class="text-[11px] text-slate-500">{{ t('profile.monoNote') }}</p>

      <!-- CASE 1 — firmware magazine: a single G-code command the
           controller interprets to swap the pen itself. -->
      <label
        v-if="colorMode === 'firmware'"
        class="block text-slate-400"
        data-test="firmware-command"
      >
        {{ t('profile.toolChangeCommand') }}
        <input
          v-model="draft.tool_change_command"
          type="text"
          placeholder="M6 T{slot}"
          class="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-slate-100"
        />
        <span class="mt-0.5 block text-[11px] text-slate-500">{{
          t('profile.firmwareCommandHint')
        }}</span>
      </label>

      <!-- CASE 2 — host macro: the Raspberry Pi streams an ordered
           sequence of G-code lines (with optional waits) to drive a
           magazine bolted onto a machine that has no native swap. -->
      <div
        v-else-if="colorMode === 'host'"
        class="space-y-2 rounded-lg border border-slate-700 bg-slate-900/50 p-3"
        data-test="host-macro-editor"
      >
        <p class="text-[11px] text-slate-400">{{ t('profile.hostMacroHint') }}</p>
        <div
          class="grid grid-cols-[1fr_5rem_1.75rem] items-center gap-2 text-[10px] text-slate-500"
        >
          <span>{{ t('profile.hostMacroSend') }}</span>
          <span>{{ t('profile.hostMacroWait') }}</span>
          <span></span>
        </div>
        <ol class="space-y-1.5">
          <li
            v-for="(step, i) in hostMacro"
            :key="i"
            class="grid grid-cols-[1fr_5rem_1.75rem] items-center gap-2"
            :data-test="`host-macro-row-${i}`"
          >
            <input
              v-model="step.send"
              type="text"
              placeholder="G0 X{slot}0 Y150"
              class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-100"
              :data-test="`host-macro-send-${i}`"
            />
            <input
              v-model.number="step.wait_ms"
              type="number"
              min="0"
              step="50"
              class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
              :data-test="`host-macro-wait-${i}`"
            />
            <button
              type="button"
              class="rounded border border-slate-700 bg-slate-800 text-slate-300 hover:bg-red-900/60 hover:text-red-200"
              :title="t('profile.hostMacroRemove')"
              :data-test="`host-macro-remove-${i}`"
              @click="removeMacroStep(i)"
            >
              −
            </button>
          </li>
        </ol>
        <p v-if="!hostMacro.length" class="text-[11px] text-amber-300" data-test="host-macro-empty">
          ⚠ {{ t('profile.hostMacroEmpty') }}
        </p>
        <button
          type="button"
          class="rounded bg-slate-700 px-2 py-1 text-xs text-slate-100 hover:bg-slate-600"
          data-test="host-macro-add"
          @click="addMacroStep"
        >
          + {{ t('profile.hostMacroAdd') }}
        </button>
        <p class="text-[10px] text-slate-500">{{ t('profile.hostMacroPlaceholders') }}</p>
      </div>
    </div>
  </details>
</template>
