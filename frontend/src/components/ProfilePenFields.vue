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

// Structured, G-code-free host swap. The operator orders high-level
// blocks; the backend compiles them using each pen's calibrated
// position (set in the magazine editor).
const STEP_KINDS: HostSwapStepKind[] = [
  'head_up',
  'head_down',
  'move_to_old_slot',
  'move_to_new_slot',
  'advance_to_slot',
  'retract_from_slot',
  'grab',
  'release',
  'dwell',
  'raw',
]

function defaultHostSwap(): HostSwapPlan {
  return {
    mechanism: 'rack',
    lock_mode: 'command',
    grab_command: 'M280 P1 S90',
    drop_command: 'M280 P1 S20',
    travel_speed_mm_s: null,
    head_up_command: null,
    head_down_command: null,
    safe_z_mm: null,
    engage_z_mm: null,
    z_min_mm: null,
    z_max_mm: null,
    clearance_axis: 'y',
    clearance_dir: '+',
    clearance_mm: 0,
    // Default sequence is crash-safe: travel to each slot's approach
    // point, advance in to act on the pen, then retract before the next
    // lateral move. (With clearance 0 the advance/retract are no-ops, so
    // the operator only needs to set the clearance distance.)
    steps: [
      { kind: 'head_up', wait_ms: 0, send: '' },
      { kind: 'move_to_old_slot', wait_ms: 0, send: '' },
      { kind: 'advance_to_slot', wait_ms: 0, send: '' },
      { kind: 'release', wait_ms: 200, send: '' },
      { kind: 'retract_from_slot', wait_ms: 0, send: '' },
      { kind: 'move_to_new_slot', wait_ms: 0, send: '' },
      { kind: 'advance_to_slot', wait_ms: 0, send: '' },
      { kind: 'grab', wait_ms: 200, send: '' },
      { kind: 'retract_from_slot', wait_ms: 0, send: '' },
      { kind: 'head_down', wait_ms: 0, send: '' },
    ],
  }
}

// Kinematic dock changer: each pen+holder is a whole tool parked in a
// fixed dock; the head couples to one at a time by sliding in/out
// (advance/retract), so there is no vertical head_up/down and the
// grab/release steps mean lock/unlock the coupling. The default lock is
// 'motion' (magnetic / kinematic), so no command is emitted.
function defaultDockSwap(): HostSwapPlan {
  return {
    mechanism: 'dock',
    lock_mode: 'motion',
    grab_command: '',
    drop_command: '',
    travel_speed_mm_s: null,
    head_up_command: null,
    head_down_command: null,
    safe_z_mm: null,
    engage_z_mm: null,
    z_min_mm: null,
    z_max_mm: null,
    // Clearance is the dock entry depth: travel to the approach point, then
    // slide this far in to seat the coupling, and back out to leave/take.
    clearance_axis: 'y',
    clearance_dir: '+',
    clearance_mm: 30,
    steps: [
      { kind: 'move_to_old_slot', wait_ms: 0, send: '' }, // approach old dock
      { kind: 'advance_to_slot', wait_ms: 0, send: '' }, // slide tool into dock
      { kind: 'release', wait_ms: 200, send: '' }, // unlock coupling
      { kind: 'retract_from_slot', wait_ms: 0, send: '' }, // back out, tool stays
      { kind: 'move_to_new_slot', wait_ms: 0, send: '' }, // approach new dock
      { kind: 'advance_to_slot', wait_ms: 0, send: '' }, // slide onto the new tool
      { kind: 'grab', wait_ms: 200, send: '' }, // lock coupling
      { kind: 'retract_from_slot', wait_ms: 0, send: '' }, // pull tool out of dock
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

// Guided host config: ① magazine type (rack vs kinematic dock) → ② action
// type (how the pen/tool is grabbed & held). Icons keep the cards scannable.
type HostMechanism = 'rack' | 'dock'
type HostAction = 'command' | 'motion'
const MECH_ICON: Record<HostMechanism, string> = { rack: '🤖', dock: '🔗' }
const ACTION_ICON: Record<HostAction, string> = { command: '🔩', motion: '🧲' }
const hostMechanism = computed<HostMechanism>(() => hostSwap.value?.mechanism ?? 'rack')
const isDock = computed(() => hostMechanism.value === 'dock')

// Switching mechanism reloads the matching preset sequence (positions are
// kept — they live on the pens, not the plan) so the step list always
// reflects the chosen hardware.
function setMechanism(m: HostMechanism): void {
  const swap = ensureHostSwap()
  if (swap.mechanism === m) return
  const preset = m === 'dock' ? defaultDockSwap() : defaultHostSwap()
  swap.mechanism = m
  swap.steps = preset.steps
  swap.lock_mode = preset.lock_mode
  swap.clearance_mm = swap.clearance_mm || preset.clearance_mm
  if (m === 'rack') {
    if (!swap.grab_command) swap.grab_command = preset.grab_command
    if (!swap.drop_command) swap.drop_command = preset.drop_command
  }
}

// ② action type. A 'command' grab (servo gripper / motorised latch) needs
// its latch commands — seed sensible defaults if the operator never set
// them. A 'motion' grab (friction / magnet) emits nothing.
function setLockMode(mode: HostAction): void {
  const swap = ensureHostSwap()
  swap.lock_mode = mode
  if (mode === 'command' && !swap.grab_command.trim() && !swap.drop_command.trim()) {
    const preset = defaultHostSwap()
    swap.grab_command = preset.grab_command
    swap.drop_command = preset.drop_command
  }
}

// Label for a step kind, mechanism-aware: on a dock, grab/release read as
// lock/unlock the coupling rather than clamp/release a pen.
function stepLabel(kind: HostSwapStepKind): string {
  if (isDock.value && (kind === 'grab' || kind === 'release')) {
    return t(`profile.hostSwap.dockStep.${kind}`)
  }
  return t(`profile.hostSwap.step.${kind}`)
}

// The advanced latch-command block only matters when a command is actually
// emitted — i.e. the ② action is 'command' (servo gripper / motorised
// latch). A 'motion' grab (friction / magnet) sends nothing.
const showsLatchCommands = computed(() => hostSwap.value?.lock_mode === 'command')

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

// Reset the step list to the current mechanism's preset — handy after
// hand-editing has drifted from a working sequence. Positions and latch
// commands are left untouched (they live elsewhere on the plan / pens).
function resetSequence(): void {
  const swap = ensureHostSwap()
  swap.steps = (swap.mechanism === 'dock' ? defaultDockSwap() : defaultHostSwap()).steps
}

// Per-slot X/Y positions, shown as a table right in the host editor so
// the operator configures everything (steps + positions + heights) in
// one place. Mirrors the magazine length so every slot has a row.
function ensurePens(): NonNullable<MachineProfile['pens']> {
  const count = Math.max(0, Math.floor(props.draft.pen_slot_count))
  const existing = props.draft.pens ?? []
  const pens = Array.from({ length: count }, (_, i) => {
    const found = existing.find((p) => p.index === i)
    return (
      found ?? {
        index: i,
        name: `Pen ${i}`,
        color: '#000000',
        installed: true,
        position: null,
        pen_up_command: null,
        pen_down_command: null,
      }
    )
  })
  props.draft.pens = pens
  return pens
}

const penRows = computed(() => {
  const count = Math.max(0, Math.floor(props.draft.pen_slot_count))
  const existing = props.draft.pens ?? []
  return Array.from({ length: count }, (_, i) => existing.find((p) => p.index === i) ?? null)
})

// Calibration status for one magazine row, surfaced in the positions
// table: a calibrated slot has an XY position; an installed slot without
// one is skipped by the swap (a real footgun), so flag it; an empty slot
// is just muted.
type CalState = 'ok' | 'warn' | 'off'
function calState(pen: { installed?: boolean; position?: unknown } | null): CalState {
  if (pen?.position != null) return 'ok'
  return pen?.installed === false ? 'off' : 'warn'
}

// How many installed pens still lack a position — the swap silently skips
// them, so warn the operator up front.
const uncalibratedCount = computed(
  () => penRows.value.filter((pen) => calState(pen) === 'warn').length,
)

// ── Sequence preview ─────────────────────────────────────────────────
// A readable, resolved preview of the compiled swap. It mirrors the
// backend HostMacroStrategy closely enough to show "what will actually
// happen" without running it, playing an *example* swap between the first
// two installed slots so the slot moves resolve to real coordinates.
interface PreviewLine {
  text: string
  detail: string
  skipped: boolean
}

function fmtNum(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(3).replace(/\.?0+$/, '')
}

// The example slots the preview narrates: the new pen is the first
// installed slot, the old pen (in hand) the next installed one (if any).
const previewExample = computed(() => {
  const installed = penRows.value
    .map((pen, i) => ({ pen, i }))
    .filter(({ pen }) => pen?.installed !== false)
    .map(({ i }) => i)
  const newIdx = installed[0] ?? 0
  const oldIdx = installed.find((i) => i !== newIdx) ?? null
  return { newIdx, oldIdx }
})

function penName(idx: number): string {
  return (props.draft.pens ?? []).find((p) => p.index === idx)?.name || `#${idx}`
}

const previewCaption = computed(() => {
  const { newIdx, oldIdx } = previewExample.value
  return oldIdx != null
    ? t('profile.hostSwap.preview.exampleSwap', { from: penName(oldIdx), to: penName(newIdx) })
    : t('profile.hostSwap.preview.exampleLoad', { to: penName(newIdx) })
})

function resolvedHead(which: 'up' | 'down', swap: HostSwapPlan): string {
  if (which === 'up') {
    if (swap.safe_z_mm != null) return `Z${fmtNum(swap.safe_z_mm)}`
    if (swap.head_up_command?.trim()) return swap.head_up_command
    return props.draft.pen_up_command
  }
  if (swap.engage_z_mm != null) return `Z${fmtNum(swap.engage_z_mm)}`
  if (swap.head_down_command?.trim()) return swap.head_down_command
  return props.draft.pen_down_command
}

const sequencePreview = computed<PreviewLine[]>(() => {
  const swap = hostSwap.value
  if (!swap) return []
  const { newIdx, oldIdx } = previewExample.value
  const sign = swap.clearance_dir === '+' ? 1 : -1
  const off = swap.clearance_mm * sign
  const dx = swap.clearance_axis === 'x' ? off : 0
  const dy = swap.clearance_axis === 'y' ? off : 0
  const posOf = (idx: number | null) =>
    idx == null ? null : ((props.draft.pens ?? []).find((p) => p.index === idx)?.position ?? null)
  const goto = (x: number, y: number) => `X${fmtNum(x)} Y${fmtNum(y)}`

  let current: number | null = null
  const lines: PreviewLine[] = []
  const add = (kind: HostSwapStepKind, detail: string, skipped: boolean, wait: number) => {
    lines.push({
      text: stepLabel(kind),
      detail: detail + (wait > 0 ? ` · ${wait}ms` : ''),
      skipped,
    })
  }

  for (const step of swap.steps) {
    const wait = step.wait_ms
    if (step.kind === 'head_up' || step.kind === 'head_down') {
      add(step.kind, resolvedHead(step.kind === 'head_up' ? 'up' : 'down', swap), false, wait)
    } else if (step.kind === 'grab' || step.kind === 'release') {
      if (swap.lock_mode === 'motion') {
        add(step.kind, t('profile.hostSwap.preview.motion'), false, wait)
      } else {
        const cmd = step.kind === 'grab' ? swap.grab_command : swap.drop_command
        add(step.kind, cmd.trim() || '—', false, wait)
      }
    } else if (step.kind === 'move_to_old_slot' || step.kind === 'move_to_new_slot') {
      const idx = step.kind === 'move_to_old_slot' ? oldIdx : newIdx
      const pos = posOf(idx)
      if (pos && idx != null) {
        current = idx
        add(step.kind, `${goto(pos.x + dx, pos.y + dy)} (${penName(idx)})`, false, wait)
      } else {
        add(step.kind, t('profile.hostSwap.preview.uncalibrated'), true, wait)
      }
    } else if (step.kind === 'advance_to_slot' || step.kind === 'retract_from_slot') {
      const pos = posOf(current)
      if (pos) {
        const target =
          step.kind === 'advance_to_slot' ? goto(pos.x, pos.y) : goto(pos.x + dx, pos.y + dy)
        add(step.kind, target, false, wait)
      } else {
        add(step.kind, t('profile.hostSwap.preview.uncalibrated'), true, wait)
      }
    } else if (step.kind === 'dwell') {
      add('dwell', `${wait}ms`, false, 0)
    } else {
      // raw
      add('raw', step.send.trim() || '—', !step.send.trim(), wait)
    }
  }
  return lines
})

function setSlotPosition(index: number, axis: 'x' | 'y', raw: string): void {
  const pens = ensurePens()
  const pen = pens.find((p) => p.index === index)
  if (!pen) return
  const thisVal = raw.trim() === '' ? null : Number(raw)
  const other = axis === 'x' ? (pen.position?.y ?? null) : (pen.position?.x ?? null)
  if (thisVal === null && other === null) {
    pen.position = null
    return
  }
  pen.position = {
    x: axis === 'x' ? (thisVal ?? 0) : (pen.position?.x ?? 0),
    y: axis === 'y' ? (thisVal ?? 0) : (pen.position?.y ?? 0),
  }
}

// Magazine servo head-height overrides: empty clears back to null (the
// profile's pen-up/-down command is used instead).
function setHeadCommand(field: 'head_up_command' | 'head_down_command', raw: string): void {
  const swap = ensureHostSwap()
  swap[field] = raw.trim() ? raw : null
}

// Z heights: edited as raw text so an empty field clears back to null
// (servo mode). ``null`` means "no real Z axis — use the servo command".
function setZ(field: 'safe_z_mm' | 'engage_z_mm' | 'z_min_mm' | 'z_max_mm', raw: string): void {
  const swap = ensureHostSwap()
  const v = raw.trim() === '' ? null : Number(raw)
  swap[field] = v !== null && Number.isFinite(v) ? v : null
}

// Clearance distance (mm) for the advance/retract hop. Empty / invalid → 0.
function setClearanceMm(raw: string): void {
  const swap = ensureHostSwap()
  const v = Number(raw)
  swap.clearance_mm = Number.isFinite(v) && v > 0 ? v : 0
}

// True when a real Z axis is in use (either height set) — the servo
// overrides are then ignored, so the editor greys them out.
const usesZAxis = computed(
  () => hostSwap.value?.safe_z_mm != null || hostSwap.value?.engage_z_mm != null,
)

// Heads-up (non-blocking) warnings around the Z heights.
const zWarning = computed<string | null>(() => {
  const s = hostSwap.value
  if (!s) return null
  const { safe_z_mm: safe, engage_z_mm: engage, z_min_mm: lo, z_max_mm: hi } = s
  if (safe != null && engage != null && engage >= safe) return 'engageAboveSafe'
  for (const z of [safe, engage]) {
    if (z == null) continue
    if (lo != null && z < lo) return 'outOfRange'
    if (hi != null && z > hi) return 'outOfRange'
  }
  return null
})

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

      <!-- CASE 2 — host magazine: a visual, G-code-free swap builder.
           The operator orders high-level blocks (move to slot, grab,
           release, head up/down, wait); the backend compiles them using
           each pen's position (set in the magazine below). A raw G-code
           block remains as an escape hatch for exotic hardware. -->
      <div
        v-else-if="colorMode === 'host' && hostSwap"
        class="space-y-3 rounded-lg border border-slate-700 bg-slate-900/50 p-3"
        data-test="host-swap-editor"
      >
        <!-- ① Magazine type: which physical changer is bolted on. Both
             compile through the same step engine; this picks the preset
             sequence + labels. -->
        <div class="space-y-1.5" data-test="host-mechanism">
          <p class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            ① {{ t('profile.hostSwap.mechanismTitle') }}
          </p>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="mech in ['rack', 'dock'] as const"
              :key="mech"
              type="button"
              class="flex flex-col gap-0.5 rounded-lg border p-2 text-left transition"
              :class="
                hostMechanism === mech
                  ? 'border-emerald-500 bg-emerald-950/40 ring-1 ring-emerald-500'
                  : 'border-slate-700 bg-slate-900/60 hover:border-slate-500'
              "
              :aria-pressed="hostMechanism === mech"
              :data-test="`host-mechanism-${mech}`"
              @click="setMechanism(mech)"
            >
              <span class="flex items-center gap-2">
                <span class="text-lg leading-none">{{ MECH_ICON[mech] }}</span>
                <span class="text-sm font-medium text-slate-200">
                  {{ t(`profile.hostSwap.mechanism.${mech}`) }}
                </span>
              </span>
              <span class="text-[11px] leading-snug text-slate-400">
                {{ t(`profile.hostSwap.mechanismHint.${mech}`) }}
              </span>
            </button>
          </div>
        </div>

        <!-- ② Action type: how the pen / tool is grabbed & held (lock_mode),
             labelled per mechanism. 'command' = servo gripper / motorised
             latch (emits the grab/drop commands below); 'motion' = friction
             / magnetic hold driven by the advance/retract motion (no
             command). -->
        <div class="space-y-1.5" data-test="host-action">
          <p class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            ② {{ t('profile.hostSwap.actionTitle') }}
          </p>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="act in ['command', 'motion'] as const"
              :key="act"
              type="button"
              class="flex flex-col gap-0.5 rounded-lg border p-2 text-left transition"
              :class="
                hostSwap.lock_mode === act
                  ? 'border-emerald-500 bg-emerald-950/40 ring-1 ring-emerald-500'
                  : 'border-slate-700 bg-slate-900/60 hover:border-slate-500'
              "
              :aria-pressed="hostSwap.lock_mode === act"
              :data-test="`host-action-${act}`"
              @click="setLockMode(act)"
            >
              <span class="flex items-center gap-2">
                <span class="text-lg leading-none">{{ ACTION_ICON[act] }}</span>
                <span class="text-sm font-medium text-slate-200">
                  {{ t(`profile.hostSwap.action.${hostMechanism}.${act}`) }}
                </span>
              </span>
              <span class="text-[11px] leading-snug text-slate-400">
                {{ t(`profile.hostSwap.actionHint.${hostMechanism}.${act}`) }}
              </span>
            </button>
          </div>
        </div>

        <!-- Per-slot magazine positions: one row per pen, X/Y in profile
             units. The "Go to slot" steps travel to these. -->
        <div class="space-y-1.5 border-t border-slate-700 pt-3" data-test="host-positions">
          <p class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            {{
              isDock
                ? t('profile.hostSwap.dockPositionsTitle')
                : t('profile.hostSwap.positionsTitle')
            }}
          </p>
          <p class="text-[11px] text-slate-500">
            {{
              isDock ? t('profile.hostSwap.dockPositionsHint') : t('profile.hostSwap.positionsHint')
            }}
          </p>
          <div
            class="grid grid-cols-[2rem_1fr_5rem_5rem_1.25rem] items-center gap-2 text-[10px] text-slate-500"
          >
            <span></span>
            <span>{{ t('profile.hostSwap.penLabel') }}</span>
            <span>X</span>
            <span>Y</span>
            <span></span>
          </div>
          <div
            v-for="(pen, i) in penRows"
            :key="i"
            class="grid grid-cols-[2rem_1fr_5rem_5rem_1.25rem] items-center gap-2"
            :data-test="`host-pos-row-${i}`"
          >
            <span class="text-center font-mono text-[11px] text-slate-500">#{{ i }}</span>
            <span class="truncate text-xs text-slate-300">{{ pen?.name || `Pen ${i}` }}</span>
            <input
              type="number"
              step="any"
              :value="pen?.position?.x ?? ''"
              placeholder="—"
              class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
              :data-test="`host-pos-x-${i}`"
              @change="(e) => setSlotPosition(i, 'x', (e.target as HTMLInputElement).value)"
            />
            <input
              type="number"
              step="any"
              :value="pen?.position?.y ?? ''"
              placeholder="—"
              class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
              :data-test="`host-pos-y-${i}`"
              @change="(e) => setSlotPosition(i, 'y', (e.target as HTMLInputElement).value)"
            />
            <span
              class="text-center text-[11px]"
              :class="{
                'text-emerald-400': calState(pen) === 'ok',
                'text-amber-400': calState(pen) === 'warn',
                'text-slate-600': calState(pen) === 'off',
              }"
              :title="t(`profile.hostSwap.cal.${calState(pen)}`)"
              :data-test="`host-pos-cal-${i}`"
            >
              {{ calState(pen) === 'ok' ? '✓' : calState(pen) === 'warn' ? '⚠' : '·' }}
            </span>
          </div>

          <p
            v-if="uncalibratedCount > 0"
            class="text-[11px] text-amber-300"
            data-test="host-uncalibrated"
          >
            ⚠ {{ t('profile.hostSwap.uncalibrated', { n: uncalibratedCount }) }}
          </p>

          <!-- Clearance: how far to back out of a slot before moving
               sideways, so the head doesn't hit the neighbouring pens.
               The slot position above is the engagement point; the
               approach point sits this far away along the chosen axis. -->
          <div class="mt-2 space-y-1 rounded border border-slate-800 bg-slate-950/40 p-2">
            <p class="text-[11px] text-slate-400">
              {{
                isDock
                  ? t('profile.hostSwap.dockClearanceHint')
                  : t('profile.hostSwap.clearanceHint')
              }}
            </p>
            <div class="flex items-end gap-2">
              <label class="block text-[11px] text-slate-400"
                >{{ t('profile.hostSwap.clearanceAxis') }}
                <select
                  v-model="hostSwap.clearance_axis"
                  class="mt-0.5 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                  data-test="host-clearance-axis"
                >
                  <option value="x">X</option>
                  <option value="y">Y</option>
                </select>
              </label>
              <label class="block text-[11px] text-slate-400"
                >{{ t('profile.hostSwap.clearanceDir') }}
                <select
                  v-model="hostSwap.clearance_dir"
                  class="mt-0.5 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                  data-test="host-clearance-dir"
                >
                  <option value="+">+</option>
                  <option value="-">−</option>
                </select>
              </label>
              <label class="block text-[11px] text-slate-400"
                >{{
                  isDock ? t('profile.hostSwap.dockEntryMm') : t('profile.hostSwap.clearanceMm')
                }}
                <input
                  type="number"
                  min="0"
                  step="any"
                  :value="hostSwap.clearance_mm"
                  class="mt-0.5 w-20 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                  data-test="host-clearance-mm"
                  @change="(e) => setClearanceMm((e.target as HTMLInputElement).value)"
                />
              </label>
            </div>
          </div>
        </div>

        <!-- Head heights — servo angle and/or a real Z axis, grouped and
             collapsible. Most servo machines just reuse the profile pen-up/
             -down, so this stays folded out of the way by default. -->
        <details class="border-t border-slate-700 pt-3" data-test="host-heights-group">
          <summary
            class="cursor-pointer text-[11px] font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-200"
          >
            {{ t('profile.hostSwap.headHeightsTitle') }}
          </summary>
          <div class="mt-3 space-y-3">
            <!-- Magazine head height (servo): the rack often sits higher
                 than the paper, so the raise/lower servo angle differs from
                 the normal pen-up/-down. Blank → reuse the profile's
                 pen-up/-down. Disabled when a real Z axis is set below. -->
            <div class="space-y-2" data-test="host-servo-heights">
              <p class="text-[11px] uppercase tracking-wider text-slate-500">
                {{ t('profile.hostSwap.servoHeightsTitle') }}
              </p>
              <p class="text-[11px] text-slate-500">{{ t('profile.hostSwap.servoHeightsHint') }}</p>
              <div class="grid grid-cols-2 gap-2" :class="{ 'opacity-40': usesZAxis }">
                <label class="block text-[11px] text-slate-400"
                  >{{ t('profile.hostSwap.headUpCommand') }}
                  <input
                    type="text"
                    :value="hostSwap.head_up_command ?? ''"
                    :placeholder="draft.pen_up_command"
                    :disabled="usesZAxis"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-[11px] text-slate-100 disabled:opacity-60"
                    data-test="host-head-up"
                    @change="
                      (e) => setHeadCommand('head_up_command', (e.target as HTMLInputElement).value)
                    "
                  />
                </label>
                <label class="block text-[11px] text-slate-400"
                  >{{ t('profile.hostSwap.headDownCommand') }}
                  <input
                    type="text"
                    :value="hostSwap.head_down_command ?? ''"
                    :placeholder="draft.pen_down_command"
                    :disabled="usesZAxis"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-[11px] text-slate-100 disabled:opacity-60"
                    data-test="host-head-down"
                    @change="
                      (e) =>
                        setHeadCommand('head_down_command', (e.target as HTMLInputElement).value)
                    "
                  />
                </label>
              </div>
              <p v-if="usesZAxis" class="text-[11px] text-slate-500">
                {{ t('profile.hostSwap.zOverridesServo') }}
              </p>
            </div>

            <!-- Z heights: travel (safe) + engage depth. Optional — only
                 for machines with a real motorised Z axis. When set they
                 take precedence over the servo commands above. -->
            <div class="space-y-2 border-t border-slate-800 pt-3" data-test="host-heights">
              <p class="text-[11px] uppercase tracking-wider text-slate-500">
                {{ t('profile.hostSwap.heightsTitle') }}
              </p>
              <p class="text-[11px] text-slate-500">{{ t('profile.hostSwap.heightsHint') }}</p>
              <div class="grid grid-cols-2 gap-2">
                <label class="block text-[11px] text-slate-400"
                  >{{ t('profile.hostSwap.safeZ') }}
                  <input
                    type="number"
                    step="any"
                    :value="hostSwap.safe_z_mm ?? ''"
                    placeholder="—"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                    data-test="host-safe-z"
                    @change="(e) => setZ('safe_z_mm', (e.target as HTMLInputElement).value)"
                  />
                </label>
                <label class="block text-[11px] text-slate-400"
                  >{{ t('profile.hostSwap.engageZ') }}
                  <input
                    type="number"
                    step="any"
                    :value="hostSwap.engage_z_mm ?? ''"
                    placeholder="—"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                    data-test="host-engage-z"
                    @change="(e) => setZ('engage_z_mm', (e.target as HTMLInputElement).value)"
                  />
                </label>
                <label class="block text-[11px] text-slate-400"
                  >{{ t('profile.hostSwap.zMin') }}
                  <input
                    type="number"
                    step="any"
                    :value="hostSwap.z_min_mm ?? ''"
                    placeholder="—"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                    data-test="host-z-min"
                    @change="(e) => setZ('z_min_mm', (e.target as HTMLInputElement).value)"
                  />
                </label>
                <label class="block text-[11px] text-slate-400"
                  >{{ t('profile.hostSwap.zMax') }}
                  <input
                    type="number"
                    step="any"
                    :value="hostSwap.z_max_mm ?? ''"
                    placeholder="—"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                    data-test="host-z-max"
                    @change="(e) => setZ('z_max_mm', (e.target as HTMLInputElement).value)"
                  />
                </label>
              </div>
              <p v-if="zWarning" class="text-[11px] text-amber-300" data-test="host-z-warning">
                ⚠ {{ t(`profile.hostSwap.${zWarning}`) }}
              </p>
            </div>
          </div>
        </details>

        <!-- Swap sequence (kept visible): generated from the magazine +
             action above, then editable step by step for fine-tuning. -->
        <div class="space-y-2 border-t border-slate-700 pt-3" data-test="host-sequence">
          <p class="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            {{ t('profile.hostSwap.sequenceTitle') }}
          </p>
          <p class="text-[11px] text-slate-400">
            {{ isDock ? t('profile.hostSwap.dockIntro') : t('profile.hostSwap.intro') }}
          </p>

          <ol class="space-y-1.5">
            <li
              v-for="(step, i) in hostSwap.steps"
              :key="i"
              class="flex items-center gap-2"
              :data-test="`host-step-${i}`"
            >
              <span class="w-5 shrink-0 text-center font-mono text-[10px] text-slate-500">{{
                i + 1
              }}</span>
              <select
                v-model="step.kind"
                class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                :data-test="`host-step-kind-${i}`"
              >
                <option v-for="k in STEP_KINDS" :key="k" :value="k">
                  {{ stepLabel(k) }}
                </option>
              </select>
              <input
                v-if="step.kind === 'raw'"
                v-model="step.send"
                type="text"
                placeholder="G4 P0.5"
                class="w-32 rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-[11px] text-slate-100"
                :data-test="`host-step-send-${i}`"
              />
              <label class="flex shrink-0 items-center gap-1 text-[10px] text-slate-500">
                <input
                  v-model.number="step.wait_ms"
                  type="number"
                  min="0"
                  step="50"
                  class="w-16 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                  :data-test="`host-step-wait-${i}`"
                />
                {{ t('profile.hostSwap.waitShort') }}
              </label>
              <button
                type="button"
                class="rounded border border-slate-700 bg-slate-800 px-1 text-slate-300 hover:bg-slate-700 disabled:opacity-30"
                :disabled="i === 0"
                :title="t('profile.hostSwap.moveUp')"
                @click="moveStep(i, -1)"
              >
                ↑
              </button>
              <button
                type="button"
                class="rounded border border-slate-700 bg-slate-800 px-1 text-slate-300 hover:bg-slate-700 disabled:opacity-30"
                :disabled="i === hostSwap.steps.length - 1"
                :title="t('profile.hostSwap.moveDown')"
                @click="moveStep(i, 1)"
              >
                ↓
              </button>
              <button
                type="button"
                class="rounded border border-slate-700 bg-slate-800 px-1.5 text-slate-300 hover:bg-red-900/60 hover:text-red-200"
                :title="t('profile.hostSwap.remove')"
                :data-test="`host-step-remove-${i}`"
                @click="removeStep(i)"
              >
                −
              </button>
            </li>
          </ol>

          <p
            v-if="!hostSwap.steps.length"
            class="text-[11px] text-amber-300"
            data-test="host-swap-empty"
          >
            ⚠ {{ t('profile.hostSwap.empty') }}
          </p>

          <div class="flex gap-2">
            <button
              type="button"
              class="rounded bg-slate-700 px-2 py-1 text-xs text-slate-100 hover:bg-slate-600"
              data-test="host-step-add"
              @click="addStep"
            >
              + {{ t('profile.hostSwap.add') }}
            </button>
            <button
              type="button"
              class="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-700"
              data-test="host-step-reset"
              @click="resetSequence"
            >
              ↺ {{ t('profile.hostSwap.resetSequence') }}
            </button>
          </div>

          <!-- Resolved preview: an example swap narrated step by step so the
               operator sees the concrete coordinates / commands without
               running it. Read-only; mirrors the backend compiler. -->
          <details
            open
            class="rounded border border-slate-800 bg-slate-950/40"
            data-test="host-preview"
          >
            <summary
              class="cursor-pointer px-2 py-1 text-[10px] uppercase tracking-wider text-slate-500 hover:text-slate-300"
            >
              {{ t('profile.hostSwap.preview.title') }}
            </summary>
            <div class="space-y-1 border-t border-slate-800 p-2">
              <p class="text-[10px] text-slate-500">{{ previewCaption }}</p>
              <ol v-if="sequencePreview.length" class="space-y-0.5">
                <li
                  v-for="(line, i) in sequencePreview"
                  :key="i"
                  class="flex items-baseline gap-2 text-[11px]"
                  :class="line.skipped ? 'text-slate-600 line-through' : 'text-slate-300'"
                  :data-test="`host-preview-line-${i}`"
                >
                  <span class="w-4 shrink-0 text-right font-mono text-[10px] text-slate-600">{{
                    i + 1
                  }}</span>
                  <span class="flex-1">{{ line.text }}</span>
                  <span class="shrink-0 font-mono text-[10px] text-slate-500">{{
                    line.detail
                  }}</span>
                </li>
              </ol>
              <p v-else class="text-[11px] text-slate-500">
                {{ t('profile.hostSwap.preview.empty') }}
              </p>
            </div>
          </details>
        </div>

        <!-- Advanced: the clamp / gripper / latch primitive (the one place
             a literal command is unavoidable). Hidden for a motion-locked
             dock, where the coupling needs no command. -->
        <details v-if="showsLatchCommands" class="rounded border border-slate-700 bg-slate-900/40">
          <summary
            class="cursor-pointer px-2 py-1 text-[10px] uppercase tracking-wider text-slate-500 hover:text-slate-300"
          >
            {{ isDock ? t('profile.hostSwap.lockAdvanced') : t('profile.hostSwap.advanced') }}
          </summary>
          <div class="grid grid-cols-2 gap-2 border-t border-slate-700 p-2">
            <label class="block text-[11px] text-slate-400"
              >{{ isDock ? t('profile.hostSwap.lockCommand') : t('profile.hostSwap.grabCommand') }}
              <input
                v-model="hostSwap.grab_command"
                type="text"
                placeholder="M280 P1 S90"
                class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-[11px] text-slate-100"
                data-test="host-grab-command"
              />
            </label>
            <label class="block text-[11px] text-slate-400"
              >{{
                isDock ? t('profile.hostSwap.unlockCommand') : t('profile.hostSwap.dropCommand')
              }}
              <input
                v-model="hostSwap.drop_command"
                type="text"
                placeholder="M280 P1 S20"
                class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-[11px] text-slate-100"
                data-test="host-drop-command"
              />
            </label>
          </div>
        </details>
      </div>
    </div>
  </details>
</template>
