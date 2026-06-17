<script setup lang="ts">
// Magazine editor — moved out of the Profile tab so the operator can
// assign colours to pen slots from the same panel that manages the
// available-colour inventory ("Couleurs" drawer tab).
//
// The colour selector lists every entry from the available-colours
// store; picking one writes its hex onto the matching pen slot. The
// ColorPicker swatch is still available so the operator can override
// with a free hex when the colour isn't (yet) in the inventory.
//
// Edits hit the backend through the same ``saveProfile`` path the
// Profile tab uses — there's no draft state here, every mutation is
// persisted immediately. The Profile tab's draft is rebuilt from
// ``profiles`` on each store reload, so an unsaved profile rename
// won't be clobbered by a pen-colour save (the watcher in
// ``useProfileDraft`` short-circuits while ``isUnsavedDraft`` is true).

import { computed, onUnmounted, reactive, ref, toRaw, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import type {
  MachineProfile,
  PenSlot,
  Point,
  TipCalibrationConfig,
  TipMeasureResponse,
} from '../api/client'
import { measureTipOffset, resetTipCalibration, setTipLight } from '../api/client'
import { useAvailableColorsStore } from '../stores/availableColors'
import { canonicalHex } from '../lib/penWidth'
import { useJobStore } from '../stores/job'
import { defaultPen, normalizePens } from '../composables/useProfileDraft'
import ColorPicker from './ColorPicker.vue'

const { t } = useI18n()
const job = useJobStore()
const { selectedProfile } = storeToRefs(job)
const availableColors = useAvailableColorsStore()

const saving = ref(false)
const error = ref<string | null>(null)
// Transient "saved" acknowledgement: every edit persists immediately, so
// a brief badge confirms the write landed without a Save button.
const justSaved = ref(false)
let savedTimer: ReturnType<typeof setTimeout> | undefined

const profile = computed(() => selectedProfile.value)

// Mirror ProfilePenFields' ceiling so a stray ``pen_slot_count`` can't
// render thousands of rows and freeze the panel.
const MAX_PEN_SLOTS = 64

const pens = computed<PenSlot[]>(() => {
  const p = profile.value
  if (!p) return []
  const existing = p.pens ?? []
  const count = Math.min(MAX_PEN_SLOTS, Math.max(0, Math.floor(p.pen_slot_count)))
  return Array.from(
    { length: count },
    (_, i) => existing.find((s) => s.index === i) ?? defaultPen(i),
  )
})

// Resolve the tool-change mode the same way ProfilePenFields does
// (capability model first, legacy field as fallback) to decide what this
// tab should show.
const colorMode = computed<'mono' | 'manual' | 'firmware' | 'host'>(() => {
  const tooling = profile.value?.capabilities?.tool_change.mode
  if (tooling === 'single_pen') return 'mono'
  if (tooling === 'manual') return 'manual'
  if (tooling === 'firmware') return 'firmware'
  if (tooling === 'host_macro') return 'host'
  switch (profile.value?.tool_change_method) {
    case 'none':
      return 'mono'
    case 'carousel':
      return 'firmware'
    case 'rack':
      return 'host'
    default:
      return 'manual'
  }
})

// The Colours tab adapts its framing to the mode: mono shows a single pen
// colour, manual a colour list (no positions — there's no physical
// magazine), firmware / host the full magazine. Only the title / hint
// differ here; the per-slot calibration is gated separately below.
const sectionTitle = computed(() => {
  if (colorMode.value === 'mono') return t('magazine.titleMono')
  if (colorMode.value === 'manual') return t('magazine.titleManual')
  return t('magazine.title')
})

const listHint = computed(() =>
  colorMode.value === 'manual' ? t('magazine.hintManual') : t('magazine.hint'),
)

// Carousel / rack profiles physically fetch the pen from a fixed slot
// position, so the calibration editor (position + per-pen up/down
// overrides) is only meaningful for those. Mono / manual hide it.
const showsCalibration = computed(
  () =>
    profile.value?.tool_change_method === 'carousel' ||
    profile.value?.tool_change_method === 'rack',
)

function matchAvailable(hex: string): string {
  // Return the canonical hex if it lives in the inventory, otherwise
  // the empty string so the select shows the "custom" sentinel option.
  const canon = canonicalHex(hex)
  return availableColors.ordered.find((c) => c.hex === canon)?.hex ?? ''
}

// Persist a mutation against a plain clone of the active profile. Every
// edit in this panel saves immediately (there's no Save button).
async function commit(mutate: (next: MachineProfile) => void): Promise<void> {
  if (!profile.value) return
  saving.value = true
  error.value = null
  try {
    // ``toRaw`` first: ``profile.value`` is a reactive proxy and
    // ``structuredClone`` throws ``DataCloneError`` on proxies, so a
    // shallow spread (which keeps the reactive ``pens`` elements) would
    // fail before the save ever ran — leaving the slot stuck on its
    // default black. Cloning the raw object yields plain data that
    // ``normalizePens`` can pad against ``pen_slot_count``.
    const next: MachineProfile = structuredClone(toRaw(profile.value))
    normalizePens(next)
    mutate(next)
    await job.saveProfile(next)
    justSaved.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (justSaved.value = false), 1500)
  } catch (err) {
    error.value =
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      t('profile.saveFailed')
  } finally {
    saving.value = false
  }
}

function patchPen(index: number, patch: Partial<PenSlot>): Promise<void> {
  return commit((next) => {
    const target = next.pens?.find((p) => p.index === index)
    if (target) Object.assign(target, patch)
  })
}

function patchProfile(patch: Partial<MachineProfile>): Promise<void> {
  return commit((next) => Object.assign(next, patch))
}

// Per-pen XY tip offset — opt-in (see ADR 0005). The toggle lives at the
// magazine level; the per-slot offset inputs only show once it's on.
const applyPenOffsets = computed(() => profile.value?.apply_pen_offsets ?? false)

function onApplyPenOffsets(enabled: boolean): void {
  void patchProfile({ apply_pen_offsets: enabled })
}

function onOffset(pen: PenSlot, axis: 'x' | 'y', raw: string): void {
  const thisVal = raw.trim() === '' ? 0 : Number(raw)
  const current = pen.xy_offset_mm ?? { x: 0, y: 0 }
  const next: Point = {
    x: axis === 'x' ? (Number.isFinite(thisVal) ? thisVal : 0) : current.x,
    y: axis === 'y' ? (Number.isFinite(thisVal) ? thisVal : 0) : current.y,
  }
  void patchPen(pen.index, { xy_offset_mm: next, offset_source: 'manual' })
}

// ── Camera tip-offset station (ADR 0005 phase 2) ─────────────────────────
// The "Measure" buttons appear once a tip_calibration block exists on the
// profile. Measuring is relative: the reference pen must be measured before
// other pens yield an offset, so the panel tracks which slots are done.
const tipConfig = computed<TipCalibrationConfig | null>(
  () => profile.value?.tip_calibration ?? null,
)
const canMeasure = computed(() => applyPenOffsets.value && tipConfig.value != null)

function defaultTipConfig(): TipCalibrationConfig {
  return {
    camera_url: '',
    station_position: null,
    reference_slot: 0,
    mm_per_pixel: 0.1,
    detector: 'dark_blob',
    dark_threshold: 80,
    roi: null,
  }
}

function onUseStation(enabled: boolean): void {
  void patchProfile({ tip_calibration: enabled ? defaultTipConfig() : null })
}

function onTipConfig(patch: Partial<TipCalibrationConfig>): void {
  const current = tipConfig.value ?? defaultTipConfig()
  void patchProfile({ tip_calibration: { ...current, ...patch } })
}

// Optional guided travel: when on (and a station position is set), the head
// is driven to the station before each measurement. Session-local — there's
// no need to persist it on the profile.
const autoMove = ref(false)
const canAutoMove = computed(() => tipConfig.value?.station_position != null)

// Optional automatic pen-fetch: load the slot's pen via a tool-change swap
// before measuring (host-macro / firmware magazines). Session-local.
const fetchPen = ref(false)

function onStation(axis: 'x' | 'y', raw: string): void {
  const cur = tipConfig.value?.station_position ?? null
  const v = raw.trim() === '' ? null : Number(raw)
  const other = axis === 'x' ? (cur?.y ?? null) : (cur?.x ?? null)
  if (v === null && other === null) {
    onTipConfig({ station_position: null })
    return
  }
  onTipConfig({
    station_position: {
      x: axis === 'x' ? (v ?? 0) : (cur?.x ?? 0),
      y: axis === 'y' ? (v ?? 0) : (cur?.y ?? 0),
    },
  })
}

function onStationZ(raw: string): void {
  const v = raw.trim() === '' ? null : Number(raw)
  onTipConfig({ station_z_mm: v !== null && Number.isFinite(v) ? v : null })
}

// Detection zone (ROI): four pixel fields. Clearing them all drops back to the
// whole frame). The backend ROI model requires width/height > 0, so we hold
// the four fields in a local draft while the operator fills them in and only
// persist a complete, valid box (otherwise null = whole frame). The draft
// re-seeds whenever the stored ROI changes (e.g. switching profiles).
const roiDraft = reactive<{ x: string; y: string; width: string; height: string }>({
  x: '',
  y: '',
  width: '',
  height: '',
})
watch(
  () => tipConfig.value?.roi ?? null,
  (roi) => {
    roiDraft.x = roi ? String(roi.x) : ''
    roiDraft.y = roi ? String(roi.y) : ''
    roiDraft.width = roi ? String(roi.width) : ''
    roiDraft.height = roi ? String(roi.height) : ''
  },
  { immediate: true },
)

function _roiNum(raw: string): number {
  const n = Math.floor(Number(raw))
  return Number.isFinite(n) && n > 0 ? n : 0
}

function onRoi(field: 'x' | 'y' | 'width' | 'height', raw: string): void {
  roiDraft[field] = raw
  const x = Math.max(0, _roiNum(roiDraft.x))
  const y = Math.max(0, _roiNum(roiDraft.y))
  const width = _roiNum(roiDraft.width)
  const height = _roiNum(roiDraft.height)
  // Persist only a complete, valid box; anything else means "whole frame".
  onTipConfig({ roi: width > 0 && height > 0 ? { x, y, width, height } : null })
}

function clearRoi(): void {
  roiDraft.x = roiDraft.y = roiDraft.width = roiDraft.height = ''
  onTipConfig({ roi: null })
}

// Camera light. ``lightDuringMeasure`` (session-local) toggles auto on/off
// around each measurement; the manual buttons are for aiming the camera.
const lightDuringMeasure = ref(false)
const hasLight = computed(() => Boolean(tipConfig.value?.light_on_command?.trim()))

function onLightCommand(field: 'light_on_command' | 'light_off_command', raw: string): void {
  onTipConfig({ [field]: raw.trim() ? raw : null })
}

async function onManualLight(on: boolean): Promise<void> {
  const cmd = on ? tipConfig.value?.light_on_command : tipConfig.value?.light_off_command
  if (!cmd?.trim()) return
  try {
    await setTipLight(cmd, on)
  } catch {
    // Non-critical (e.g. disconnected); the measurement path reports errors.
  }
}

// Per-slot transient measurement feedback (busy + last message/confidence).
interface MeasureState {
  busy: boolean
  message: string
  ok: boolean
  // Annotated frame (data URL) for visual confirmation of the detected tip.
  image?: string | null
}
const measureState = reactive<Record<number, MeasureState>>({})

function describeMeasurement(m: TipMeasureResponse): { message: string; ok: boolean } {
  if (!m.found) {
    return { message: m.message || t('magazine.measureNotFound'), ok: false }
  }
  if (m.is_reference) {
    return {
      message: t('magazine.measureRefDone', { c: Math.round(m.confidence * 100) }),
      ok: true,
    }
  }
  if (!m.reference_measured || !m.offset_mm) {
    return { message: t('magazine.measureNeedRef'), ok: false }
  }
  return {
    message: t('magazine.measureApplied', {
      x: m.offset_mm.x.toFixed(2),
      y: m.offset_mm.y.toFixed(2),
      c: Math.round(m.confidence * 100),
    }),
    ok: true,
  }
}

async function onMeasure(pen: PenSlot): Promise<void> {
  const cfg = tipConfig.value
  if (!cfg) return
  measureState[pen.index] = { busy: true, message: '', ok: false }
  try {
    const m = await measureTipOffset({
      slot: pen.index,
      camera_url: cfg.camera_url,
      mm_per_pixel: cfg.mm_per_pixel,
      reference_slot: cfg.reference_slot,
      dark_threshold: cfg.dark_threshold,
      roi: cfg.roi,
      fetch_pen: fetchPen.value,
      move_to_station: autoMove.value && cfg.station_position != null,
      station_position: cfg.station_position ?? null,
      station_z_mm: cfg.station_z_mm ?? null,
      profile_name: profile.value?.name ?? null,
      light: lightDuringMeasure.value,
      light_on_command: cfg.light_on_command ?? null,
      light_off_command: cfg.light_off_command ?? null,
    })
    // Apply the measured offset when we have one (reference pen → (0,0),
    // others → their delta). A not-found / no-reference result only reports.
    if (m.found && (m.is_reference || m.offset_mm)) {
      const offset: Point = m.offset_mm ?? { x: 0, y: 0 }
      await patchPen(pen.index, { xy_offset_mm: offset, offset_source: 'vision' })
    }
    const { message, ok } = describeMeasurement(m)
    measureState[pen.index] = { busy: false, message, ok, image: m.annotated_image }
  } catch (err) {
    const detail =
      (err as { response?: { data?: { message?: string } } })?.response?.data?.message ??
      t('magazine.measureFailed')
    measureState[pen.index] = { busy: false, message: detail, ok: false }
  }
}

async function onResetMeasurements(): Promise<void> {
  try {
    await resetTipCalibration()
    for (const k of Object.keys(measureState)) delete measureState[Number(k)]
  } catch {
    // A reset failure is non-critical; the next measure run still works.
  }
}

function onSelectColor(index: number, value: string): void {
  if (!value) return
  void patchPen(index, { color: value })
}

function onCustomColor(index: number, hex: string): void {
  void patchPen(index, { color: hex })
}

function onName(index: number, name: string): void {
  void patchPen(index, { name })
}

function onInstalled(index: number, installed: boolean): void {
  void patchPen(index, { installed })
}

function onPenCommand(
  index: number,
  key: 'pen_up_command' | 'pen_down_command',
  raw: string,
): void {
  // Empty string clears the override so the slot falls back to the
  // profile-level command (the backend treats null as "use default").
  const value = raw.trim() ? raw : null
  void patchPen(index, { [key]: value } as Partial<PenSlot>)
}

function onPosition(pen: PenSlot, axis: 'x' | 'y', raw: string): void {
  const thisVal = raw.trim() === '' ? null : Number(raw)
  const otherVal = axis === 'x' ? (pen.position?.y ?? null) : (pen.position?.x ?? null)
  // Both axes blank → uncalibrated (null), falls back to no routing.
  if (thisVal === null && otherVal === null) {
    void patchPen(pen.index, { position: null })
    return
  }
  const next: Point = {
    x: axis === 'x' ? (thisVal ?? 0) : (pen.position?.x ?? 0),
    y: axis === 'y' ? (thisVal ?? 0) : (pen.position?.y ?? 0),
  }
  void patchPen(pen.index, { position: next })
}

function displayLabel(name: string, hex: string): string {
  return name.trim() ? `${name} · ${hex}` : hex
}

onUnmounted(() => clearTimeout(savedTimer))
</script>

<template>
  <section class="space-y-2 rounded-lg border border-slate-700 bg-slate-800 p-3">
    <div class="flex items-baseline justify-between">
      <p class="text-[10px] uppercase tracking-wider text-slate-400">
        {{ sectionTitle }}
      </p>
      <span class="flex items-center gap-2">
        <span v-if="justSaved" class="text-[10px] text-emerald-400" data-test="magazine-saved"
          >✓ {{ t('magazine.saved') }}</span
        >
        <span v-if="profile" class="text-[10px] text-slate-500">
          {{ profile.name }}
        </span>
      </span>
    </div>

    <p v-if="!profile" class="text-xs text-slate-500">{{ t('magazine.noProfile') }}</p>

    <template v-else>
      <!-- Mono: a single pen → just its colour, no slots / magazine. -->
      <div v-if="colorMode === 'mono'" class="space-y-1.5" data-test="magazine-mono">
        <p class="text-[11px] text-slate-500">{{ t('magazine.monoHint') }}</p>
        <div
          class="flex items-center gap-2 rounded border border-slate-700 bg-slate-900/60 px-2 py-1.5"
        >
          <ColorPicker
            :model-value="pens[0]?.color ?? '#000000'"
            :label="t('availableColors.pickColor')"
            swatch-class="h-7 w-9"
            :disabled="saving"
            @update:model-value="(hex) => onCustomColor(0, hex)"
          />
          <select
            class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 disabled:opacity-60"
            :value="matchAvailable(pens[0]?.color ?? '')"
            :disabled="saving || !availableColors.ordered.length"
            @change="(e) => onSelectColor(0, (e.target as HTMLSelectElement).value)"
          >
            <option value="" disabled>
              {{
                availableColors.ordered.length
                  ? t('magazine.customColor', { hex: pens[0]?.color ?? '#000000' })
                  : t('magazine.noAvailable')
              }}
            </option>
            <option v-for="opt in availableColors.ordered" :key="opt.color_id" :value="opt.hex">
              {{ displayLabel(opt.name, opt.hex) }}
            </option>
          </select>
        </div>
      </div>

      <!-- Manual / firmware / host: per-slot list. Manual is a colour list
           (no positions — no physical magazine); firmware / host add the
           per-slot calibration block (gated by ``showsCalibration``). -->
      <template v-else>
        <p class="text-[11px] text-slate-500">{{ listHint }}</p>

        <!-- Optional per-pen tip-offset compensation. Only meaningful for a
             multi-pen magazine (carousel / rack), so it rides alongside the
             per-slot calibration block and is off by default. -->
        <div
          v-if="showsCalibration"
          class="rounded border border-slate-800 bg-slate-950/40 px-2 py-1.5"
          data-test="magazine-offsets-toggle"
        >
          <label class="flex items-center gap-2 text-[11px] text-slate-300">
            <input
              type="checkbox"
              :checked="applyPenOffsets"
              class="rounded border-slate-600 bg-slate-900"
              :disabled="saving"
              data-test="apply-pen-offsets"
              @change="(e) => onApplyPenOffsets((e.target as HTMLInputElement).checked)"
            />
            {{ t('magazine.applyOffsets') }}
          </label>
          <p class="mt-0.5 text-[11px] text-slate-500">{{ t('magazine.applyOffsetsHint') }}</p>

          <!-- Optional camera measurement station: when configured, each slot
               gets a "Measure" button that locates the tip and fills the
               offset automatically. Without it, offsets are typed by hand. -->
          <div v-if="applyPenOffsets" class="mt-2 border-t border-slate-800 pt-2">
            <label class="flex items-center gap-2 text-[11px] text-slate-300">
              <input
                type="checkbox"
                :checked="tipConfig != null"
                class="rounded border-slate-600 bg-slate-900"
                :disabled="saving"
                data-test="use-tip-station"
                @change="(e) => onUseStation((e.target as HTMLInputElement).checked)"
              />
              {{ t('magazine.useStation') }}
            </label>

            <div
              v-if="tipConfig"
              class="mt-1.5 grid grid-cols-2 gap-2"
              data-test="tip-station-config"
            >
              <label class="col-span-2 block text-[11px] text-slate-400"
                >{{ t('magazine.cameraUrl') }}
                <input
                  type="text"
                  :value="tipConfig.camera_url"
                  placeholder="http://localhost:8080/?action=snapshot"
                  :disabled="saving"
                  class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-[11px] text-slate-100"
                  data-test="tip-camera-url"
                  @change="(e) => onTipConfig({ camera_url: (e.target as HTMLInputElement).value })"
                />
              </label>
              <label class="block text-[11px] text-slate-400"
                >{{ t('magazine.mmPerPixel') }}
                <input
                  type="number"
                  step="any"
                  min="0"
                  :value="tipConfig.mm_per_pixel"
                  :disabled="saving"
                  class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                  data-test="tip-mm-per-pixel"
                  @change="
                    (e) =>
                      onTipConfig({ mm_per_pixel: Number((e.target as HTMLInputElement).value) })
                  "
                />
              </label>
              <label class="block text-[11px] text-slate-400"
                >{{ t('magazine.referenceSlot') }}
                <input
                  type="number"
                  step="1"
                  min="0"
                  :value="tipConfig.reference_slot"
                  :disabled="saving"
                  class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                  data-test="tip-reference-slot"
                  @change="
                    (e) =>
                      onTipConfig({
                        reference_slot: Math.max(
                          0,
                          Math.floor(Number((e.target as HTMLInputElement).value)),
                        ),
                      })
                  "
                />
              </label>
              <label class="block text-[11px] text-slate-400"
                >{{ t('magazine.stationX') }}
                <input
                  type="number"
                  step="any"
                  :value="tipConfig.station_position?.x ?? ''"
                  placeholder="—"
                  :disabled="saving"
                  class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                  data-test="tip-station-x"
                  @change="(e) => onStation('x', (e.target as HTMLInputElement).value)"
                />
              </label>
              <label class="block text-[11px] text-slate-400"
                >{{ t('magazine.stationY') }}
                <input
                  type="number"
                  step="any"
                  :value="tipConfig.station_position?.y ?? ''"
                  placeholder="—"
                  :disabled="saving"
                  class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                  data-test="tip-station-y"
                  @change="(e) => onStation('y', (e.target as HTMLInputElement).value)"
                />
              </label>
              <label class="col-span-2 block text-[11px] text-slate-400"
                >{{ t('magazine.stationZ') }}
                <input
                  type="number"
                  step="any"
                  :value="tipConfig.station_z_mm ?? ''"
                  placeholder="—"
                  :disabled="saving"
                  class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                  data-test="tip-station-z"
                  @change="(e) => onStationZ((e.target as HTMLInputElement).value)"
                />
              </label>
              <label class="col-span-2 flex items-center gap-2 text-[11px] text-slate-300">
                <input
                  v-model="fetchPen"
                  type="checkbox"
                  class="rounded border-slate-600 bg-slate-900"
                  :disabled="saving"
                  data-test="tip-fetch-pen"
                />
                {{ t('magazine.fetchPen') }}
              </label>
              <label
                class="col-span-2 flex items-center gap-2 text-[11px]"
                :class="canAutoMove ? 'text-slate-300' : 'text-slate-600'"
              >
                <input
                  v-model="autoMove"
                  type="checkbox"
                  class="rounded border-slate-600 bg-slate-900"
                  :disabled="saving || !canAutoMove"
                  data-test="tip-auto-move"
                />
                {{ t('magazine.autoMove') }}
              </label>

              <!-- Detection zone (ROI): restrict the search to a pixel box so
                   clutter elsewhere in the frame is ignored. Blank = whole
                   frame. -->
              <div class="col-span-2 rounded border border-slate-800 bg-slate-950/40 p-2">
                <p class="mb-1 text-[11px] uppercase tracking-wider text-slate-500">
                  {{ t('magazine.roiTitle') }}
                </p>
                <div class="grid grid-cols-4 gap-1.5" data-test="tip-roi">
                  <label class="block text-[10px] text-slate-400"
                    >X
                    <input
                      type="number"
                      min="0"
                      step="1"
                      :value="roiDraft.x"
                      placeholder="—"
                      :disabled="saving"
                      class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-[11px] text-slate-100"
                      data-test="tip-roi-x"
                      @change="(e) => onRoi('x', (e.target as HTMLInputElement).value)"
                    />
                  </label>
                  <label class="block text-[10px] text-slate-400"
                    >Y
                    <input
                      type="number"
                      min="0"
                      step="1"
                      :value="roiDraft.y"
                      placeholder="—"
                      :disabled="saving"
                      class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-[11px] text-slate-100"
                      data-test="tip-roi-y"
                      @change="(e) => onRoi('y', (e.target as HTMLInputElement).value)"
                    />
                  </label>
                  <label class="block text-[10px] text-slate-400"
                    >W
                    <input
                      type="number"
                      min="0"
                      step="1"
                      :value="roiDraft.width"
                      placeholder="—"
                      :disabled="saving"
                      class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-[11px] text-slate-100"
                      data-test="tip-roi-w"
                      @change="(e) => onRoi('width', (e.target as HTMLInputElement).value)"
                    />
                  </label>
                  <label class="block text-[10px] text-slate-400"
                    >H
                    <input
                      type="number"
                      min="0"
                      step="1"
                      :value="roiDraft.height"
                      placeholder="—"
                      :disabled="saving"
                      class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-[11px] text-slate-100"
                      data-test="tip-roi-h"
                      @change="(e) => onRoi('height', (e.target as HTMLInputElement).value)"
                    />
                  </label>
                </div>
                <button
                  v-if="tipConfig.roi"
                  type="button"
                  class="mt-1 text-[10px] text-slate-400 underline hover:text-slate-200"
                  :disabled="saving"
                  data-test="tip-roi-clear"
                  @click="clearRoi"
                >
                  {{ t('magazine.roiClear') }}
                </button>
              </div>

              <!-- Camera light (On/Off): commands + auto on/off around a
                   measurement + manual buttons for aiming. -->
              <div class="col-span-2 rounded border border-slate-800 bg-slate-950/40 p-2">
                <p class="mb-1 text-[11px] uppercase tracking-wider text-slate-500">
                  {{ t('magazine.lightTitle') }}
                </p>
                <div class="grid grid-cols-2 gap-1.5">
                  <label class="block text-[10px] text-slate-400"
                    >{{ t('magazine.lightOnCommand') }}
                    <input
                      type="text"
                      :value="tipConfig.light_on_command ?? ''"
                      placeholder="M355 S1"
                      :disabled="saving"
                      class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-1.5 py-1 font-mono text-[11px] text-slate-100"
                      data-test="tip-light-on-cmd"
                      @change="
                        (e) =>
                          onLightCommand('light_on_command', (e.target as HTMLInputElement).value)
                      "
                    />
                  </label>
                  <label class="block text-[10px] text-slate-400"
                    >{{ t('magazine.lightOffCommand') }}
                    <input
                      type="text"
                      :value="tipConfig.light_off_command ?? ''"
                      placeholder="M355 S0"
                      :disabled="saving"
                      class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-1.5 py-1 font-mono text-[11px] text-slate-100"
                      data-test="tip-light-off-cmd"
                      @change="
                        (e) =>
                          onLightCommand('light_off_command', (e.target as HTMLInputElement).value)
                      "
                    />
                  </label>
                </div>
                <div class="mt-1.5 flex items-center gap-2">
                  <button
                    type="button"
                    class="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-700 disabled:opacity-40"
                    :disabled="saving || !hasLight"
                    data-test="tip-light-on"
                    @click="onManualLight(true)"
                  >
                    💡 {{ t('magazine.lightOn') }}
                  </button>
                  <button
                    type="button"
                    class="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700 disabled:opacity-40"
                    :disabled="saving || !hasLight"
                    data-test="tip-light-off"
                    @click="onManualLight(false)"
                  >
                    {{ t('magazine.lightOff') }}
                  </button>
                </div>
                <label
                  class="mt-1.5 flex items-center gap-2 text-[11px]"
                  :class="hasLight ? 'text-slate-300' : 'text-slate-600'"
                >
                  <input
                    v-model="lightDuringMeasure"
                    type="checkbox"
                    class="rounded border-slate-600 bg-slate-900"
                    :disabled="saving || !hasLight"
                    data-test="tip-light-during"
                  />
                  {{ t('magazine.lightDuringMeasure') }}
                </label>
              </div>

              <button
                type="button"
                class="col-span-2 justify-self-start rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
                :disabled="saving"
                data-test="tip-reset"
                @click="onResetMeasurements"
              >
                ↺ {{ t('magazine.resetMeasurements') }}
              </button>
              <p class="col-span-2 text-[11px] text-slate-500">{{ t('magazine.stationHint') }}</p>
            </div>
          </div>
        </div>

        <ul v-if="pens.length" class="space-y-1.5">
          <li
            v-for="pen in pens"
            :key="pen.index"
            class="rounded border border-slate-700 bg-slate-900/60 px-2 py-1.5"
          >
            <div class="flex items-center gap-2">
              <span class="w-6 shrink-0 text-center font-mono text-[11px] text-slate-500">
                #{{ pen.index }}
              </span>

              <ColorPicker
                :model-value="pen.color"
                :label="t('availableColors.pickColor')"
                swatch-class="h-7 w-9"
                :disabled="saving"
                @update:model-value="(hex) => onCustomColor(pen.index, hex)"
              />

              <select
                class="min-w-0 flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100 disabled:opacity-60"
                :value="matchAvailable(pen.color)"
                :disabled="saving || !availableColors.ordered.length"
                @change="(e) => onSelectColor(pen.index, (e.target as HTMLSelectElement).value)"
              >
                <option value="" disabled>
                  {{
                    availableColors.ordered.length
                      ? t('magazine.customColor', { hex: pen.color })
                      : t('magazine.noAvailable')
                  }}
                </option>
                <option v-for="opt in availableColors.ordered" :key="opt.color_id" :value="opt.hex">
                  {{ displayLabel(opt.name, opt.hex) }}
                </option>
              </select>

              <input
                type="text"
                :value="pen.name"
                :placeholder="`Pen ${pen.index}`"
                class="w-28 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                :disabled="saving"
                @change="(e) => onName(pen.index, (e.target as HTMLInputElement).value)"
              />

              <label class="flex shrink-0 items-center gap-1 text-[11px] text-slate-400">
                <input
                  type="checkbox"
                  :checked="pen.installed"
                  class="rounded border-slate-600 bg-slate-900"
                  :disabled="saving"
                  @change="(e) => onInstalled(pen.index, (e.target as HTMLInputElement).checked)"
                />
                {{ t('profile.installed') }}
              </label>
            </div>

            <!-- Per-slot calibration: magazine position + pen-up/down
               overrides. Only carousel / rack machines fetch pens from a
               fixed position, so the block is hidden for mono / manual. -->
            <details
              v-if="showsCalibration"
              class="mt-1.5 rounded border border-slate-800 bg-slate-950/40"
              :data-test="`pen-calibration-${pen.index}`"
            >
              <summary
                class="cursor-pointer px-2 py-1 text-[10px] uppercase tracking-wider text-slate-500 hover:text-slate-300"
              >
                {{ t('magazine.calibration') }}
              </summary>
              <div class="grid grid-cols-2 gap-2 border-t border-slate-800 p-2">
                <label class="block text-[11px] text-slate-400"
                  >{{ t('magazine.posX') }}
                  <input
                    type="number"
                    step="any"
                    :value="pen.position?.x ?? ''"
                    :disabled="saving"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                    @change="(e) => onPosition(pen, 'x', (e.target as HTMLInputElement).value)"
                  />
                </label>
                <label class="block text-[11px] text-slate-400"
                  >{{ t('magazine.posY') }}
                  <input
                    type="number"
                    step="any"
                    :value="pen.position?.y ?? ''"
                    :disabled="saving"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                    @change="(e) => onPosition(pen, 'y', (e.target as HTMLInputElement).value)"
                  />
                </label>
                <label class="block text-[11px] text-slate-400"
                  >{{ t('magazine.penUpOverride') }}
                  <input
                    type="text"
                    :value="pen.pen_up_command ?? ''"
                    :placeholder="t('magazine.useProfileDefault')"
                    :disabled="saving"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-100"
                    @change="
                      (e) =>
                        onPenCommand(
                          pen.index,
                          'pen_up_command',
                          (e.target as HTMLInputElement).value,
                        )
                    "
                  />
                </label>
                <label class="block text-[11px] text-slate-400"
                  >{{ t('magazine.penDownOverride') }}
                  <input
                    type="text"
                    :value="pen.pen_down_command ?? ''"
                    :placeholder="t('magazine.useProfileDefault')"
                    :disabled="saving"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-xs text-slate-100"
                    @change="
                      (e) =>
                        onPenCommand(
                          pen.index,
                          'pen_down_command',
                          (e.target as HTMLInputElement).value,
                        )
                    "
                  />
                </label>

                <!-- Per-pen XY tip offset (only when the magazine opts in). -->
                <template v-if="applyPenOffsets">
                  <label class="block text-[11px] text-slate-400"
                    >{{ t('magazine.offsetX') }}
                    <input
                      type="number"
                      step="any"
                      :value="pen.xy_offset_mm?.x ?? 0"
                      :disabled="saving"
                      class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                      :data-test="`pen-offset-x-${pen.index}`"
                      @change="(e) => onOffset(pen, 'x', (e.target as HTMLInputElement).value)"
                    />
                  </label>
                  <label class="block text-[11px] text-slate-400"
                    >{{ t('magazine.offsetY') }}
                    <input
                      type="number"
                      step="any"
                      :value="pen.xy_offset_mm?.y ?? 0"
                      :disabled="saving"
                      class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-100"
                      :data-test="`pen-offset-y-${pen.index}`"
                      @change="(e) => onOffset(pen, 'y', (e.target as HTMLInputElement).value)"
                    />
                  </label>
                  <p class="col-span-2 text-[11px] text-slate-500">
                    {{ t('magazine.offsetHint') }}
                  </p>

                  <!-- Camera measurement: present the pen at the station and
                       fill its offset automatically (reference pen first). -->
                  <div v-if="canMeasure" class="col-span-2 flex items-center gap-2">
                    <button
                      type="button"
                      class="rounded border border-emerald-700 bg-emerald-950/40 px-2 py-1 text-[11px] text-emerald-200 hover:bg-emerald-900/50 disabled:opacity-50"
                      :disabled="saving || measureState[pen.index]?.busy"
                      :data-test="`pen-measure-${pen.index}`"
                      @click="onMeasure(pen)"
                    >
                      {{
                        measureState[pen.index]?.busy
                          ? t('magazine.measuring')
                          : '📷 ' + t('magazine.measure')
                      }}
                    </button>
                    <span
                      v-if="measureState[pen.index]?.message"
                      class="text-[11px]"
                      :class="measureState[pen.index]?.ok ? 'text-emerald-400' : 'text-amber-400'"
                      :data-test="`pen-measure-msg-${pen.index}`"
                    >
                      {{ measureState[pen.index]?.message }}
                    </span>
                  </div>
                  <img
                    v-if="measureState[pen.index]?.image"
                    :src="measureState[pen.index]!.image!"
                    :alt="t('magazine.measurePreviewAlt')"
                    class="col-span-2 max-h-40 w-auto rounded border border-slate-700"
                    :data-test="`pen-measure-preview-${pen.index}`"
                  />
                </template>
              </div>
            </details>
          </li>
        </ul>

        <p v-else class="text-xs text-slate-500">{{ t('magazine.empty') }}</p>
      </template>

      <p v-if="error" class="text-[11px] text-red-400">{{ error }}</p>
    </template>
  </section>
</template>
