<script setup lang="ts">
// Offset-camera settings — the full per-pen XY tip-offset feature, grouped
// under Settings → Cameras. Presented as a guided flow: a master toggle, then
// (1) camera + live preview, (2) scale, (3) per-pen measurement, with the
// rarely-touched knobs (detection zone, station position, GPIO light) folded
// under an Advanced disclosure. Edits persist immediately to the active
// profile via the same saveProfile path the magazine editor uses.

import { computed, onMounted, onUnmounted, reactive, ref, toRaw, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import type {
  MachineProfile,
  PenSlot,
  Point,
  TipCalibrationConfig,
  TipMeasureResponse,
} from '../api/client'
import {
  calibrateTipScale,
  getTipGpio,
  measureTipOffset,
  resetTipCalibration,
  setTipLight,
} from '../api/client'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'
import { defaultPen, normalizePens } from '../composables/useProfileDraft'
import CameraPreview from './CameraPreview.vue'

const { t } = useI18n()
const job = useJobStore()
const ui = useUiStore()
const { selectedProfile } = storeToRefs(job)

const saving = ref(false)
const error = ref<string | null>(null)
const justSaved = ref(false)
let savedTimer: ReturnType<typeof setTimeout> | undefined

const profile = computed(() => selectedProfile.value)
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

// Per-pen offsets only make sense on a multi-pen machine.
const isMultiPen = computed(() => pens.value.length > 1)

async function commit(mutate: (next: MachineProfile) => void): Promise<void> {
  if (!profile.value) return
  saving.value = true
  error.value = null
  try {
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

const applyPenOffsets = computed(() => profile.value?.apply_pen_offsets ?? false)

function onApplyPenOffsets(enabled: boolean): void {
  void patchProfile({ apply_pen_offsets: enabled })
}

function onOffset(pen: PenSlot, axis: 'x' | 'y', raw: string): void {
  const v = raw.trim() === '' ? 0 : Number(raw)
  const current = pen.xy_offset_mm ?? { x: 0, y: 0 }
  const next: Point = {
    x: axis === 'x' ? (Number.isFinite(v) ? v : 0) : current.x,
    y: axis === 'y' ? (Number.isFinite(v) ? v : 0) : current.y,
  }
  void patchPen(pen.index, { xy_offset_mm: next, offset_source: 'manual' })
}

// ── Station config (profile-level) ───────────────────────────────────────
const tipConfig = computed<TipCalibrationConfig | null>(
  () => profile.value?.tip_calibration ?? null,
)
const canMeasure = computed(() => applyPenOffsets.value && tipConfig.value != null)
const workshopCameras = computed(() => ui.cameras.filter((c) => c.enabled && c.url.trim()))

// A magazine (carousel / rack, or a firmware / host-macro changer) can fetch
// the pen automatically. Without one — a manual / single-holder machine — the
// operator presents each pen at the station by hand. Per-pen offsets work in
// both cases; only the auto-fetch affordance is magazine-specific.
const hasMagazine = computed(() => {
  const mode = profile.value?.capabilities?.tool_change.mode
  if (mode === 'firmware' || mode === 'host_macro') return true
  const method = profile.value?.tool_change_method
  return method === 'carousel' || method === 'rack'
})

const scaleLabel = computed(() =>
  tipConfig.value
    ? t('offsetCamera.scaleSet', { v: tipConfig.value.mm_per_pixel })
    : t('offsetCamera.scaleUnset'),
)

// One-word status per pen, driving a coloured badge in the measure list.
function penStatus(pen: PenSlot): { label: string; cls: string } {
  if (tipConfig.value && pen.index === tipConfig.value.reference_slot) {
    return { label: t('offsetCamera.statusReference'), cls: 'bg-sky-900/60 text-sky-200' }
  }
  if (pen.offset_source === 'vision') {
    return { label: t('offsetCamera.statusMeasured'), cls: 'bg-emerald-900/60 text-emerald-200' }
  }
  if (pen.offset_source === 'manual') {
    return { label: t('offsetCamera.statusManual'), cls: 'bg-slate-700 text-slate-200' }
  }
  return { label: t('offsetCamera.statusPending'), cls: 'bg-slate-800 text-slate-400' }
}

function defaultTipConfig(): TipCalibrationConfig {
  return {
    camera_url: '',
    station_position: null,
    reference_slot: 0,
    mm_per_pixel: 0.1,
    detector: 'dark_blob',
    dark_threshold: 80,
    samples: 1,
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

function onPickCamera(url: string): void {
  if (url) onTipConfig({ camera_url: url })
}

function onSamples(raw: string): void {
  const v = Math.floor(Number(raw))
  onTipConfig({ samples: Number.isFinite(v) ? Math.min(20, Math.max(1, v)) : 1 })
}

// Session-local per-measurement options.
const autoMove = ref(false)
const canAutoMove = computed(() => tipConfig.value?.station_position != null)
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

// Detection zone (ROI): the backend requires width/height > 0, so the four
// fields live in a local draft and only persist as a complete, valid box.
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
  onTipConfig({ roi: width > 0 && height > 0 ? { x, y, width, height } : null })
}

function clearRoi(): void {
  roiDraft.x = roiDraft.y = roiDraft.width = roiDraft.height = ''
  onTipConfig({ roi: null })
}

// Camera light via a Pi GPIO pin.
const lightDuringMeasure = ref(false)
const gpioPins = ref<number[]>([])
const gpioAvailable = ref(false)
const lightPin = computed(() => tipConfig.value?.light_gpio_pin ?? null)
const hasLight = computed(() => lightPin.value != null)
const lightState = reactive<{ message: string; ok: boolean }>({ message: '', ok: false })

// A configured station light is almost always meant to be used for the
// measurement itself. Default to the safe/user-friendly path when the operator
// selects a pin, and clear it when the pin is removed.
watch(
  lightPin,
  (pin) => {
    if (pin == null) {
      lightDuringMeasure.value = false
      lightState.message = ''
      return
    }
    lightDuringMeasure.value = true
  },
  { immediate: true },
)

async function loadGpio(): Promise<void> {
  try {
    const info = await getTipGpio()
    gpioPins.value = info.pins
    gpioAvailable.value = info.available
  } catch {
    gpioPins.value = []
    gpioAvailable.value = false
  }
}

function onLightPin(raw: string): void {
  const parsed = Math.floor(Number(raw))
  const v = raw === '' || !Number.isFinite(parsed) ? null : parsed
  onTipConfig({ light_gpio_pin: v })
}

function onLightActiveHigh(activeHigh: boolean): void {
  onTipConfig({ light_active_high: activeHigh })
}

async function onManualLight(on: boolean): Promise<void> {
  const pin = lightPin.value
  if (pin == null) return
  lightState.message = ''
  try {
    await setTipLight(pin, on, tipConfig.value?.light_active_high ?? true)
    lightState.ok = true
    lightState.message = t(on ? 'offsetCamera.lightOnOk' : 'offsetCamera.lightOffOk')
  } catch {
    lightState.ok = false
    lightState.message = t('offsetCamera.lightFailed')
  }
}

// Operator-facing readiness chips. They keep the guided flow simple by showing
// what is ready, what is optional, and what still blocks a camera measurement.
interface ReadinessItem {
  key: string
  ok: boolean
  optional: boolean
}

const readiness = computed<ReadinessItem[]>(() => {
  const cfg = tipConfig.value
  if (!cfg) return []
  return [
    { key: 'camera', ok: cfg.camera_url.trim().length > 0, optional: false },
    { key: 'scale', ok: cfg.mm_per_pixel > 0, optional: false },
    {
      key: 'reference',
      ok: pens.value.some((p) => p.installed && p.index === cfg.reference_slot),
      optional: false,
    },
    { key: 'zone', ok: cfg.roi != null, optional: true },
    { key: 'light', ok: hasLight.value, optional: true },
  ]
})

function readinessClass(item: ReadinessItem): string {
  if (item.ok) return 'border-emerald-800 bg-emerald-950/40 text-emerald-200'
  if (item.optional) return 'border-slate-700 bg-slate-900/60 text-slate-400'
  return 'border-amber-800 bg-amber-950/30 text-amber-200'
}

const blockingReadiness = computed(() => readiness.value.find((item) => !item.optional && !item.ok))
const cameraMeasurementReady = computed(() => canMeasure.value && blockingReadiness.value == null)
const setupHint = computed(() =>
  blockingReadiness.value
    ? t(`offsetCamera.next.${blockingReadiness.value.key}`)
    : t('offsetCamera.next.ready'),
)

// ── Measurement ──────────────────────────────────────────────────────────
interface MeasureState {
  busy: boolean
  message: string
  ok: boolean
  image?: string | null
}
const measureState = reactive<Record<number, MeasureState>>({})

// Below this detection confidence a measurement is treated as untrusted: it's
// shown (with the frame) but NOT written, so a blurry / wrong-blob detection
// can't silently corrupt a pen's offset.
const MIN_CONFIDENCE = 0.35

// A measured offset larger than this (mm from the reference tip) is almost
// certainly a mis-detection — adjacent pen tips sit a few mm apart, not
// centimetres. The result is still applied (it cleared the confidence gate),
// but flagged so the operator can sanity-check the marked frame.
const SUSPICIOUS_OFFSET_MM = 50

// When several frames are averaged (samples > 1), how far apart they landed is
// a repeatability signal. Above this the feed is too unstable to trust the
// reading — the result is still shown, with a nudge to re-measure.
const SUSPICIOUS_SPREAD_MM = 1.5

// Repeatability suffix for an averaged measurement: a quiet "± X mm" normally,
// an explicit warning when the frames disagreed too much. Empty for a single
// frame (spread 0 / absent).
function spreadNote(m: TipMeasureResponse): string {
  const s = m.spread_mm
  if (s == null || s <= 0) return ''
  if (s > SUSPICIOUS_SPREAD_MM) return ' ' + t('offsetCamera.unstable', { mm: s.toFixed(2) })
  return ' ' + t('offsetCamera.repeatability', { mm: s.toFixed(2) })
}

function describeMeasurement(m: TipMeasureResponse): { message: string; ok: boolean } {
  if (!m.found) return { message: m.message || t('magazine.measureNotFound'), ok: false }
  if (m.confidence < MIN_CONFIDENCE)
    return {
      message: t('offsetCamera.lowConfidence', { c: Math.round(m.confidence * 100) }),
      ok: false,
    }
  if (m.is_reference)
    return {
      message: t('magazine.measureRefDone', { c: Math.round(m.confidence * 100) }) + spreadNote(m),
      ok: true,
    }
  if (!m.reference_measured || !m.offset_mm)
    return { message: t('magazine.measureNeedRef'), ok: false }
  let message = t('magazine.measureApplied', {
    x: m.offset_mm.x.toFixed(2),
    y: m.offset_mm.y.toFixed(2),
    c: Math.round(m.confidence * 100),
  })
  const magnitude = Math.hypot(m.offset_mm.x, m.offset_mm.y)
  if (magnitude > SUSPICIOUS_OFFSET_MM)
    message += ' ' + t('offsetCamera.largeOffset', { mm: Math.round(magnitude) })
  return { message: message + spreadNote(m), ok: true }
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
      samples: cfg.samples,
      roi: cfg.roi,
      fetch_pen: fetchPen.value,
      move_to_station: autoMove.value && cfg.station_position != null,
      station_position: cfg.station_position ?? null,
      station_z_mm: cfg.station_z_mm ?? null,
      profile_name: profile.value?.name ?? null,
      light: lightDuringMeasure.value,
      light_gpio_pin: cfg.light_gpio_pin ?? null,
      light_active_high: cfg.light_active_high ?? true,
    })
    const { message, ok } = describeMeasurement(m)
    // Only write a trusted result (found + confident enough).
    if (ok && (m.is_reference || m.offset_mm)) {
      const offset: Point = m.offset_mm ?? { x: 0, y: 0 }
      await patchPen(pen.index, { xy_offset_mm: offset, offset_source: 'vision' })
    }
    measureState[pen.index] = { busy: false, message, ok, image: m.annotated_image }
  } catch (err) {
    const detail =
      (err as { response?: { data?: { message?: string } } })?.response?.data?.message ??
      t('magazine.measureFailed')
    measureState[pen.index] = { busy: false, message: detail, ok: false }
  }
}

// Clear a pen's offset back to zero / unmeasured.
function onClearOffset(pen: PenSlot): void {
  void patchPen(pen.index, { xy_offset_mm: { x: 0, y: 0 }, offset_source: 'unset' })
}

const installedPens = computed(() => pens.value.filter((p) => p.installed))
function isPenMeasured(pen: PenSlot): boolean {
  return !!pen.offset_source && pen.offset_source !== 'unset'
}
const measuredCount = computed(() => installedPens.value.filter(isPenMeasured).length)

// ── Test detection (dry run) ───────────────────────────────────────────────
// Run the detector on the current view WITHOUT writing any offset, so the
// operator can tune lighting / zone / threshold before committing. Measures
// the reference slot's view; the result is reported, not applied.
const testState = reactive<{ busy: boolean; message: string; ok: boolean; image?: string | null }>({
  busy: false,
  message: '',
  ok: false,
})

async function onTestDetection(): Promise<void> {
  const cfg = tipConfig.value
  if (!cfg) return
  testState.busy = true
  testState.message = ''
  try {
    const m = await measureTipOffset({
      slot: cfg.reference_slot,
      camera_url: cfg.camera_url,
      mm_per_pixel: cfg.mm_per_pixel,
      reference_slot: cfg.reference_slot,
      dark_threshold: cfg.dark_threshold,
      samples: cfg.samples,
      roi: cfg.roi,
      light: lightDuringMeasure.value,
      light_gpio_pin: cfg.light_gpio_pin ?? null,
      light_active_high: cfg.light_active_high ?? true,
    })
    testState.image = m.annotated_image
    const stable = (m.spread_mm ?? 0) <= SUSPICIOUS_SPREAD_MM
    testState.ok = m.found && m.confidence >= MIN_CONFIDENCE && stable
    testState.message = m.found
      ? t('offsetCamera.testResult', { c: Math.round(m.confidence * 100) }) + spreadNote(m)
      : m.message || t('magazine.measureNotFound')
  } catch (err) {
    testState.ok = false
    testState.message =
      (err as { response?: { data?: { message?: string } } })?.response?.data?.message ??
      t('magazine.measureFailed')
  } finally {
    testState.busy = false
  }
}

// ── Guided sequence ────────────────────────────────────────────────────────
// Walk the operator through measuring every installed pen, reference first.
// On a manual machine each step prompts to present the pen by hand; with a
// magazine the fetch toggle loads it. Advances only on a successful measure.
const guided = ref(false)
const guideStep = ref(0)
const guideOrder = computed<number[]>(() => {
  if (!tipConfig.value) return []
  const refSlot = tipConfig.value.reference_slot
  const installed = pens.value.filter((p) => p.installed).map((p) => p.index)
  if (!installed.includes(refSlot)) return installed
  return [refSlot, ...installed.filter((i) => i !== refSlot)]
})
const guidePen = computed<PenSlot | null>(() => {
  const idx = guideOrder.value[guideStep.value]
  return idx == null ? null : (pens.value.find((p) => p.index === idx) ?? null)
})
const nextGuideIndex = computed(() => {
  const next = guideOrder.value.findIndex((idx) => {
    const pen = pens.value.find((p) => p.index === idx)
    return pen != null && !isPenMeasured(pen)
  })
  return next >= 0 ? next : 0
})
const nextGuidePen = computed<PenSlot | null>(() => {
  const idx = guideOrder.value[nextGuideIndex.value]
  return idx == null ? null : (pens.value.find((p) => p.index === idx) ?? null)
})
const guideStartText = computed(() =>
  nextGuidePen.value && measuredCount.value < installedPens.value.length
    ? t('offsetCamera.guidedStartNext', {
        pen: nextGuidePen.value.name || `Pen ${nextGuidePen.value.index}`,
      })
    : t('offsetCamera.guidedStartReview'),
)

function measureActionLabel(pen: PenSlot): string {
  return isPenMeasured(pen) ? t('offsetCamera.remeasureButton') : t('offsetCamera.measureButton')
}

function startGuide(): void {
  guideStep.value = nextGuideIndex.value
  guided.value = true
}

function cancelGuide(): void {
  guided.value = false
}

async function measureGuided(): Promise<void> {
  const pen = guidePen.value
  if (!pen) return
  await onMeasure(pen)
  if (!measureState[pen.index]?.ok) return // failed — let the operator retry
  if (guideStep.value < guideOrder.value.length - 1) guideStep.value++
  else guided.value = false
}

async function onResetMeasurements(): Promise<void> {
  try {
    await resetTipCalibration()
    for (const k of Object.keys(measureState)) delete measureState[Number(k)]
  } catch {
    // Non-critical.
  }
}

// mm-per-pixel assistant.
const knownMm = ref(10)
const scaleState = reactive<{ busy: boolean; message: string; ok: boolean; image?: string | null }>(
  {
    busy: false,
    message: '',
    ok: false,
  },
)

async function onCalibrateScale(): Promise<void> {
  const cfg = tipConfig.value
  if (!cfg || !(knownMm.value > 0)) return
  scaleState.busy = true
  scaleState.message = ''
  try {
    const r = await calibrateTipScale({
      camera_url: cfg.camera_url,
      known_mm: knownMm.value,
      dark_threshold: cfg.dark_threshold,
      roi: cfg.roi,
    })
    scaleState.image = r.annotated_image
    if (r.found && r.mm_per_pixel) {
      onTipConfig({ mm_per_pixel: Number(r.mm_per_pixel.toFixed(5)) })
      scaleState.ok = true
      scaleState.message = t('magazine.scaleApplied', {
        v: r.mm_per_pixel.toFixed(4),
        px: Math.round(Math.max(r.width_px ?? 0, r.height_px ?? 0)),
      })
    } else {
      scaleState.ok = false
      scaleState.message = r.message || t('magazine.scaleNotFound')
    }
  } catch (err) {
    scaleState.ok = false
    scaleState.message =
      (err as { response?: { data?: { message?: string } } })?.response?.data?.message ??
      t('magazine.scaleFailed')
  } finally {
    scaleState.busy = false
  }
}

onMounted(loadGpio)
onUnmounted(() => clearTimeout(savedTimer))
</script>

<template>
  <section class="space-y-2 rounded-lg border border-slate-700 bg-slate-800 p-3 text-xs">
    <div class="flex items-baseline justify-between">
      <h3 class="text-[11px] uppercase tracking-wider text-slate-500">
        {{ t('offsetCamera.title') }}
      </h3>
      <span class="flex items-center gap-2">
        <span v-if="justSaved" class="text-[10px] text-emerald-400" data-test="offset-saved"
          >✓ {{ t('magazine.saved') }}</span
        >
        <span v-if="profile" class="text-[10px] text-slate-500">{{ profile.name }}</span>
      </span>
    </div>
    <p class="text-[11px] text-slate-500">{{ t('offsetCamera.hint') }}</p>

    <p v-if="!profile" class="text-[11px] text-slate-500">{{ t('magazine.noProfile') }}</p>
    <p v-else-if="!isMultiPen" class="text-[11px] text-slate-500">
      {{ t('offsetCamera.needsMagazine') }}
    </p>

    <!-- Per-pen offsets work on any multi-pen machine. A magazine auto-fetches
         the pen (``fetch_pen`` toggle); without one, the operator presents each
         pen at the station by hand — the ``manualPresent`` / ``guidedPresent``
         hints below drive that path. So the full flow renders whenever the
         machine has more than one pen, magazine or not. -->
    <template v-else>
      <!-- Master switch. -->
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
      <p class="text-[11px] text-slate-500">{{ t('magazine.applyOffsetsHint') }}</p>

      <div v-if="applyPenOffsets" class="space-y-2">
        <!-- ── Step 1+2: the camera (optional). ──────────────────────── -->
        <div class="rounded-lg border border-slate-700 bg-slate-900/40 p-2">
          <label class="flex items-center gap-2 text-[11px] text-slate-300">
            <input
              type="checkbox"
              :checked="tipConfig != null"
              class="rounded border-slate-600 bg-slate-900"
              :disabled="saving"
              data-test="use-tip-station"
              @change="(e) => onUseStation((e.target as HTMLInputElement).checked)"
            />
            {{ t('offsetCamera.enable') }}
          </label>

          <div v-if="tipConfig" class="mt-2 space-y-3">
            <!-- Step 1 — camera + live preview. -->
            <div class="space-y-1.5">
              <p class="text-[11px] font-semibold text-slate-300">{{ t('offsetCamera.step1') }}</p>
              <p class="text-[11px] text-slate-500">{{ t('offsetCamera.step1Hint') }}</p>
              <select
                v-if="workshopCameras.length"
                class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                :disabled="saving"
                data-test="tip-camera-source"
                @change="(e) => onPickCamera((e.target as HTMLSelectElement).value)"
              >
                <option value="">{{ t('magazine.cameraCustom') }}</option>
                <option v-for="(c, i) in workshopCameras" :key="i" :value="c.url">
                  {{ c.label || t('magazine.cameraN', { n: i + 1 }) }}
                </option>
              </select>
              <input
                type="text"
                :value="tipConfig.camera_url"
                placeholder="http://localhost:8080/?action=snapshot"
                :disabled="saving"
                class="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-[11px] text-slate-100"
                data-test="tip-camera-url"
                @change="(e) => onTipConfig({ camera_url: (e.target as HTMLInputElement).value })"
              />
              <CameraPreview
                :url="tipConfig.camera_url"
                :label="t('offsetCamera.title')"
                :roi="tipConfig.roi"
                editable
                height="md"
                @update:roi="(r) => onTipConfig({ roi: r })"
              />
              <div class="grid grid-cols-2 gap-1.5 sm:grid-cols-5" data-test="tip-readiness">
                <span
                  v-for="item in readiness"
                  :key="item.key"
                  class="rounded border px-2 py-1 text-[10px]"
                  :class="readinessClass(item)"
                  :data-test="`tip-ready-${item.key}`"
                >
                  {{ item.ok ? '✓' : item.optional ? '·' : '⚠' }}
                  {{ t(`offsetCamera.ready.${item.key}`) }}
                </span>
              </div>
              <!-- Dry-run detection: tune framing / zone / threshold without
                   writing any offset. -->
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="rounded border border-slate-600 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-700 disabled:opacity-50"
                  :disabled="saving || testState.busy || !tipConfig.camera_url.trim()"
                  data-test="tip-test"
                  @click="onTestDetection"
                >
                  {{
                    testState.busy
                      ? t('magazine.measuring')
                      : '🔍 ' + t('offsetCamera.testDetection')
                  }}
                </button>
                <span
                  v-if="testState.message"
                  class="text-[11px]"
                  :class="testState.ok ? 'text-emerald-400' : 'text-amber-400'"
                  data-test="tip-test-msg"
                  >{{ testState.message }}</span
                >
              </div>
              <img
                v-if="testState.image"
                :src="testState.image"
                :alt="t('offsetCamera.testDetection')"
                class="max-h-40 w-auto rounded border border-slate-700"
                data-test="tip-test-preview"
              />
            </div>

            <!-- Step 2 — scale. -->
            <div class="space-y-1.5 border-t border-slate-800 pt-2">
              <div class="flex items-center justify-between">
                <p class="text-[11px] font-semibold text-slate-300">
                  {{ t('offsetCamera.step2') }}
                </p>
                <span
                  class="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300"
                  data-test="scale-chip"
                  >{{ scaleLabel }}</span
                >
              </div>
              <p class="text-[11px] text-slate-500">{{ t('offsetCamera.step2Hint') }}</p>
              <div class="flex flex-wrap items-end gap-2">
                <label class="block text-[10px] text-slate-400"
                  >{{ t('magazine.mmPerPixel') }}
                  <input
                    type="number"
                    step="any"
                    min="0"
                    :value="tipConfig.mm_per_pixel"
                    :disabled="saving"
                    class="mt-0.5 w-24 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                    data-test="tip-mm-per-pixel"
                    @change="
                      (e) =>
                        onTipConfig({ mm_per_pixel: Number((e.target as HTMLInputElement).value) })
                    "
                  />
                </label>
                <span class="pb-1 text-[10px] text-slate-500">{{
                  t('offsetCamera.step2Hint')
                }}</span>
              </div>
              <div class="rounded border border-slate-800 bg-slate-950/40 p-2">
                <p class="mb-1 text-[10px] uppercase tracking-wider text-slate-500">
                  {{ t('magazine.scaleTitle') }}
                </p>
                <p class="mb-1 text-[11px] text-slate-500">{{ t('magazine.scaleHint') }}</p>
                <div class="flex items-end gap-2">
                  <label class="block text-[10px] text-slate-400"
                    >{{ t('magazine.scaleKnownMm') }}
                    <input
                      v-model.number="knownMm"
                      type="number"
                      step="any"
                      min="0"
                      :disabled="saving || scaleState.busy"
                      class="mt-0.5 w-24 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                      data-test="tip-scale-known-mm"
                    />
                  </label>
                  <button
                    type="button"
                    class="rounded border border-emerald-700 bg-emerald-950/40 px-2 py-1 text-[11px] text-emerald-200 hover:bg-emerald-900/50 disabled:opacity-50"
                    :disabled="saving || scaleState.busy || !(knownMm > 0)"
                    data-test="tip-scale-measure"
                    @click="onCalibrateScale"
                  >
                    {{
                      scaleState.busy ? t('magazine.measuring') : '📐 ' + t('magazine.scaleMeasure')
                    }}
                  </button>
                </div>
                <p
                  v-if="scaleState.message"
                  class="mt-1 text-[11px]"
                  :class="scaleState.ok ? 'text-emerald-400' : 'text-amber-400'"
                  data-test="tip-scale-msg"
                >
                  {{ scaleState.message }}
                </p>
                <img
                  v-if="scaleState.image"
                  :src="scaleState.image"
                  :alt="t('magazine.scaleTitle')"
                  class="mt-1 max-h-40 w-auto rounded border border-slate-700"
                  data-test="tip-scale-preview"
                />
              </div>
            </div>

            <!-- Advanced — detection zone, station position, light. -->
            <details class="border-t border-slate-800 pt-2" data-test="tip-advanced">
              <summary
                class="cursor-pointer text-[11px] font-semibold text-slate-400 hover:text-slate-200"
              >
                {{ t('offsetCamera.advanced') }}
              </summary>
              <div class="mt-2 grid grid-cols-2 gap-2">
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
                  >{{ t('magazine.darkThreshold') }}
                  <input
                    type="number"
                    min="0"
                    max="255"
                    step="1"
                    :value="tipConfig.dark_threshold"
                    :disabled="saving"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                    data-test="tip-dark-threshold"
                    @change="
                      (e) =>
                        onTipConfig({
                          dark_threshold: Math.min(
                            255,
                            Math.max(0, Math.floor(Number((e.target as HTMLInputElement).value))),
                          ),
                        })
                    "
                  />
                </label>
                <label class="block text-[11px] text-slate-400"
                  >{{ t('offsetCamera.samples') }}
                  <input
                    type="number"
                    min="1"
                    max="20"
                    step="1"
                    :value="tipConfig.samples ?? 1"
                    :disabled="saving"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
                    data-test="tip-samples"
                    @change="(e) => onSamples((e.target as HTMLInputElement).value)"
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
                <label
                  v-if="hasMagazine"
                  class="col-span-2 flex items-center gap-2 text-[11px] text-slate-300"
                >
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

                <!-- Detection zone (ROI). -->
                <div class="col-span-2 rounded border border-slate-800 bg-slate-950/40 p-2">
                  <p class="mb-1 text-[10px] uppercase tracking-wider text-slate-500">
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

                <!-- Camera light via a Pi GPIO pin. -->
                <div class="col-span-2 rounded border border-slate-800 bg-slate-950/40 p-2">
                  <p class="mb-1 text-[10px] uppercase tracking-wider text-slate-500">
                    {{ t('magazine.lightTitle') }}
                  </p>
                  <div class="grid grid-cols-2 gap-1.5">
                    <label class="block text-[10px] text-slate-400"
                      >{{ t('magazine.lightGpioPin') }}
                      <select
                        :value="tipConfig.light_gpio_pin ?? ''"
                        :disabled="saving"
                        class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-[11px] text-slate-100"
                        data-test="tip-light-pin"
                        @change="(e) => onLightPin((e.target as HTMLSelectElement).value)"
                      >
                        <option value="">{{ t('magazine.lightNoPin') }}</option>
                        <option v-for="p in gpioPins" :key="p" :value="p">GPIO {{ p }}</option>
                      </select>
                    </label>
                    <label class="flex items-end gap-2 pb-1 text-[10px] text-slate-400">
                      <input
                        type="checkbox"
                        :checked="tipConfig.light_active_high ?? true"
                        class="rounded border-slate-600 bg-slate-900"
                        :disabled="saving"
                        data-test="tip-light-active-high"
                        @change="(e) => onLightActiveHigh((e.target as HTMLInputElement).checked)"
                      />
                      {{ t('magazine.lightActiveHigh') }}
                    </label>
                  </div>
                  <p
                    v-if="!gpioAvailable"
                    class="mt-1 text-[11px] text-amber-400"
                    data-test="tip-gpio-warn"
                  >
                    ⚠ {{ t('magazine.gpioUnavailable') }}
                  </p>
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
                    <span
                      v-if="lightState.message"
                      class="text-[11px]"
                      :class="lightState.ok ? 'text-emerald-400' : 'text-amber-400'"
                      data-test="tip-light-msg"
                    >
                      {{ lightState.message }}
                    </span>
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
              </div>
            </details>
          </div>
        </div>

        <!-- ── Step 3: per-pen offsets + measurement. ────────────────── -->
        <div class="rounded-lg border border-slate-700 bg-slate-900/40 p-2">
          <div class="flex items-center justify-between">
            <p class="text-[11px] font-semibold text-slate-300">{{ t('offsetCamera.step3') }}</p>
            <span
              class="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300"
              data-test="offset-progress"
              >{{ t('offsetCamera.progress', { k: measuredCount, n: installedPens.length }) }}</span
            >
          </div>
          <p class="mb-1 text-[11px] text-slate-500">
            {{ canMeasure ? t('offsetCamera.step3Hint') : t('magazine.offsetHint') }}
          </p>
          <p
            v-if="canMeasure"
            class="mb-2 rounded border px-2 py-1 text-[11px]"
            :class="
              cameraMeasurementReady
                ? 'border-emerald-800 bg-emerald-950/30 text-emerald-200'
                : 'border-amber-800 bg-amber-950/30 text-amber-200'
            "
            data-test="offset-next-action"
          >
            {{ cameraMeasurementReady ? '✓' : '⚠' }} {{ setupHint }}
          </p>
          <p
            v-if="canMeasure && !hasMagazine"
            class="mb-1 text-[11px] text-sky-300"
            data-test="manual-present-hint"
          >
            🖐 {{ t('offsetCamera.manualPresent') }}
          </p>

          <!-- Guided sequence: a one-pen-at-a-time wizard with a live view. -->
          <button
            v-if="canMeasure && !guided"
            type="button"
            class="mb-2 rounded border border-sky-700 bg-sky-950/40 px-2 py-1 text-[11px] text-sky-200 hover:bg-sky-900/50 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="saving || !cameraMeasurementReady"
            data-test="guide-start"
            :title="setupHint"
            @click="startGuide"
          >
            🧭 {{ guideStartText }}
          </button>

          <div
            v-if="guided && guidePen"
            class="mb-2 space-y-2 rounded-lg border border-sky-800 bg-sky-950/20 p-2"
            data-test="guide-panel"
          >
            <div class="flex items-center justify-between">
              <p class="text-[11px] font-semibold text-sky-200" data-test="guide-step">
                {{
                  t('offsetCamera.guidedStep', {
                    k: guideStep + 1,
                    n: guideOrder.length,
                    pen: guidePen.name || `Pen ${guidePen.index}`,
                  })
                }}
              </p>
              <span
                class="rounded px-1.5 py-0.5 text-[9px] font-medium"
                :class="penStatus(guidePen).cls"
                >{{ penStatus(guidePen).label }}</span
              >
            </div>
            <p v-if="!hasMagazine" class="text-[11px] text-sky-300">
              🖐
              {{
                t('offsetCamera.guidedPresent', { pen: guidePen.name || `Pen ${guidePen.index}` })
              }}
            </p>
            <CameraPreview
              v-if="tipConfig"
              :url="tipConfig.camera_url"
              :label="t('offsetCamera.title')"
              :roi="tipConfig.roi"
              height="md"
            />
            <p
              v-if="measureState[guidePen.index]?.message"
              class="text-[11px]"
              :class="measureState[guidePen.index]?.ok ? 'text-emerald-400' : 'text-amber-400'"
              data-test="guide-msg"
            >
              {{ measureState[guidePen.index]?.message }}
            </p>
            <img
              v-if="measureState[guidePen.index]?.image"
              :src="measureState[guidePen.index]!.image!"
              :alt="t('magazine.measurePreviewAlt')"
              class="max-h-40 w-auto rounded border border-slate-700"
              data-test="guide-result"
            />
            <div class="flex items-center gap-2">
              <button
                type="button"
                class="rounded border border-emerald-700 bg-emerald-950/40 px-2 py-1 text-[11px] text-emerald-200 hover:bg-emerald-900/50 disabled:opacity-50"
                :disabled="saving || !cameraMeasurementReady || measureState[guidePen.index]?.busy"
                data-test="guide-measure"
                :title="setupHint"
                @click="measureGuided"
              >
                {{
                  measureState[guidePen.index]?.busy
                    ? t('magazine.measuring')
                    : '📷 ' + t('offsetCamera.guidedMeasure')
                }}
              </button>
              <button
                type="button"
                class="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-700"
                data-test="guide-cancel"
                @click="cancelGuide"
              >
                {{ t('offsetCamera.guidedDone') }}
              </button>
            </div>
          </div>

          <ul v-if="!guided" class="space-y-1.5">
            <li
              v-for="pen in pens"
              :key="pen.index"
              class="rounded border border-slate-700 bg-slate-900/60 px-2 py-1.5"
              :data-test="`offset-row-${pen.index}`"
            >
              <div class="grid grid-cols-[2rem_1fr_auto] items-center gap-2">
                <span class="text-center font-mono text-[11px] text-slate-500"
                  >#{{ pen.index }}</span
                >
                <span class="truncate text-[11px] text-slate-300">{{
                  pen.name || `Pen ${pen.index}`
                }}</span>
                <span
                  class="rounded px-1.5 py-0.5 text-[9px] font-medium"
                  :class="penStatus(pen).cls"
                  :data-test="`offset-status-${pen.index}`"
                  >{{ penStatus(pen).label }}</span
                >
              </div>
              <div class="mt-1 grid grid-cols-[1fr_1fr_auto] items-end gap-2">
                <label class="block text-[10px] text-slate-400"
                  >{{ t('magazine.offsetX') }}
                  <input
                    type="number"
                    step="any"
                    :value="pen.xy_offset_mm?.x ?? 0"
                    :disabled="saving"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-[11px] text-slate-100"
                    :data-test="`pen-offset-x-${pen.index}`"
                    @change="(e) => onOffset(pen, 'x', (e.target as HTMLInputElement).value)"
                  />
                </label>
                <label class="block text-[10px] text-slate-400"
                  >{{ t('magazine.offsetY') }}
                  <input
                    type="number"
                    step="any"
                    :value="pen.xy_offset_mm?.y ?? 0"
                    :disabled="saving"
                    class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-1.5 py-1 text-[11px] text-slate-100"
                    :data-test="`pen-offset-y-${pen.index}`"
                    @change="(e) => onOffset(pen, 'y', (e.target as HTMLInputElement).value)"
                  />
                </label>
                <div class="flex items-center gap-1">
                  <button
                    v-if="canMeasure"
                    type="button"
                    class="rounded border border-emerald-700 bg-emerald-950/40 px-2 py-1 text-[11px] text-emerald-200 hover:bg-emerald-900/50 disabled:opacity-50"
                    :disabled="saving || !cameraMeasurementReady || measureState[pen.index]?.busy"
                    :data-test="`pen-measure-${pen.index}`"
                    :title="setupHint"
                    @click="onMeasure(pen)"
                  >
                    {{
                      measureState[pen.index]?.busy
                        ? t('magazine.measuring')
                        : '📷 ' + measureActionLabel(pen)
                    }}
                  </button>
                  <button
                    v-if="pen.offset_source && pen.offset_source !== 'unset'"
                    type="button"
                    class="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-400 hover:bg-slate-700 hover:text-slate-200 disabled:opacity-50"
                    :disabled="saving"
                    :title="t('offsetCamera.clearOffset')"
                    :aria-label="t('offsetCamera.clearOffset')"
                    :data-test="`pen-clear-${pen.index}`"
                    @click="onClearOffset(pen)"
                  >
                    ✕
                  </button>
                </div>
              </div>
              <p
                v-if="measureState[pen.index]?.message"
                class="mt-1 text-[11px]"
                :class="measureState[pen.index]?.ok ? 'text-emerald-400' : 'text-amber-400'"
                :data-test="`pen-measure-msg-${pen.index}`"
              >
                {{ measureState[pen.index]?.message }}
              </p>
              <img
                v-if="measureState[pen.index]?.image"
                :src="measureState[pen.index]!.image!"
                :alt="t('magazine.measurePreviewAlt')"
                class="mt-1 max-h-40 w-auto rounded border border-slate-700"
                :data-test="`pen-measure-preview-${pen.index}`"
              />
            </li>
          </ul>
        </div>
      </div>

      <p v-if="error" class="text-[11px] text-red-400">{{ error }}</p>
    </template>
  </section>
</template>
