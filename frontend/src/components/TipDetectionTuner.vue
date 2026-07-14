<script setup lang="ts">
// Detection tuner for the offset camera — one compact surface where the
// operator adjusts what the detector sees and gets immediate feedback.
//
// Left to right, the tuning loop is: watch the live feed (drag a detection
// zone directly on it), pick the tip type (dark tip on light background or
// the inverse), slide the threshold, choose how many frames to average —
// then read the result: a dry-run detection with a confidence meter (the 35%
// trust gate is marked on the bar), a repeatability note and the annotated
// frame. With "auto re-test" on, every committed adjustment re-runs the
// dry-run so the meter tracks the knobs — no offset is ever written from
// here (the backend call is flagged dry_run).
//
// All edits are emitted as config patches; persistence stays with the parent
// (OffsetCameraSettings), which owns the profile save path.

import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { TipCalibrationConfig } from '../api/client'
import { measureTipOffset } from '../api/client'
import CameraPreview from './CameraPreview.vue'

const props = withDefaults(
  defineProps<{
    config: TipCalibrationConfig
    disabled?: boolean
    // Forwarded to the dry-run call so the test sees the same lighting as a
    // real measurement (the GPIO pin/polarity come from the config itself).
    lightDuringMeasure?: boolean
  }>(),
  { disabled: false, lightDuringMeasure: false },
)

const emit = defineEmits<{ (e: 'update:config', patch: Partial<TipCalibrationConfig>): void }>()

const { t } = useI18n()

// Same trust gate as the parent's measurement flow: below this the result is
// shown but would not be applied, so the meter marks it.
const MIN_CONFIDENCE = 0.35
const SUSPICIOUS_SPREAD_MM = 1.5

const tipStyle = computed<'dark' | 'light'>(() => props.config.tip_style ?? 'dark')

function onTipStyle(raw: string): void {
  emit('update:config', { tip_style: raw === 'light' ? 'light' : 'dark' })
}

// Threshold: a local draft renders slider drags live without a profile save
// per pixel; the value is committed (emitted) on release / field change.
const thresholdDraft = ref(props.config.dark_threshold)
watch(
  () => props.config.dark_threshold,
  (v) => (thresholdDraft.value = v),
)

function _clampThreshold(raw: string): number {
  const v = Math.floor(Number(raw))
  return Number.isFinite(v) ? Math.min(255, Math.max(0, v)) : 80
}

function onThresholdInput(raw: string): void {
  thresholdDraft.value = _clampThreshold(raw)
}

function onThresholdCommit(raw: string): void {
  const v = _clampThreshold(raw)
  thresholdDraft.value = v
  if (v !== props.config.dark_threshold) emit('update:config', { dark_threshold: v })
}

function onSamples(raw: string): void {
  const v = Math.floor(Number(raw))
  emit('update:config', { samples: Number.isFinite(v) ? Math.min(20, Math.max(1, v)) : 1 })
}

// ── Dry-run detection + feedback ──────────────────────────────────────────
const testState = reactive<{
  busy: boolean
  message: string
  ok: boolean
  // null until a test has run; then 0..1 (0 when nothing was found).
  confidence: number | null
  image: string | null
}>({ busy: false, message: '', ok: false, confidence: null, image: null })

function spreadNote(spread: number | null | undefined): string {
  if (spread == null || spread <= 0) return ''
  if (spread > SUSPICIOUS_SPREAD_MM)
    return ' ' + t('offsetCamera.unstable', { mm: spread.toFixed(2) })
  return ' ' + t('offsetCamera.repeatability', { mm: spread.toFixed(2) })
}

async function runTest(): Promise<void> {
  const cfg = props.config
  if (!cfg.camera_url.trim() || testState.busy) return
  testState.busy = true
  testState.message = ''
  try {
    const m = await measureTipOffset({
      slot: cfg.reference_slot,
      camera_url: cfg.camera_url,
      mm_per_pixel: cfg.mm_per_pixel,
      reference_slot: cfg.reference_slot,
      tip_style: cfg.tip_style ?? 'dark',
      dark_threshold: cfg.dark_threshold,
      samples: cfg.samples,
      roi: cfg.roi,
      // Dry run: report the detection but never store it, so tuning can't
      // silently replace the session's reference measurement.
      dry_run: true,
      light: props.lightDuringMeasure,
      light_gpio_pin: cfg.light_gpio_pin ?? null,
      light_active_high: cfg.light_active_high ?? true,
    })
    testState.image = m.annotated_image
    testState.confidence = m.found ? m.confidence : 0
    const stable = (m.spread_mm ?? 0) <= SUSPICIOUS_SPREAD_MM
    testState.ok = m.found && m.confidence >= MIN_CONFIDENCE && stable
    testState.message = m.found
      ? t('offsetCamera.testResult', { c: Math.round(m.confidence * 100) }) +
        spreadNote(m.spread_mm)
      : m.message || t('magazine.measureNotFound')
  } catch (err) {
    testState.ok = false
    testState.confidence = null
    testState.message =
      (err as { response?: { data?: { message?: string } } })?.response?.data?.message ??
      t('magazine.measureFailed')
  } finally {
    testState.busy = false
  }
}

// Auto re-test: any committed tuning change re-runs the dry-run (debounced,
// so a burst of edits costs one camera round-trip) and the meter follows.
const autoTest = ref(false)
let retestTimer: ReturnType<typeof setTimeout> | undefined

watch(
  () => [props.config.tip_style, props.config.dark_threshold, props.config.samples, props.config.roi],
  () => {
    if (!autoTest.value) return
    clearTimeout(retestTimer)
    retestTimer = setTimeout(() => void runTest(), 600)
  },
  { deep: true },
)

function onAutoTest(enabled: boolean): void {
  autoTest.value = enabled
  if (enabled) void runTest()
}

onBeforeUnmount(() => clearTimeout(retestTimer))

// Confidence meter: percentage width + a colour that mirrors the trust gate.
const confidencePct = computed(() =>
  testState.confidence == null ? 0 : Math.round(Math.min(1, Math.max(0, testState.confidence)) * 100),
)
const meterClass = computed(() =>
  (testState.confidence ?? 0) >= MIN_CONFIDENCE ? 'bg-emerald-500' : 'bg-amber-500',
)
</script>

<template>
  <div class="space-y-1.5">
    <p class="text-[11px] font-semibold text-slate-300">{{ t('offsetCamera.tuneTitle') }}</p>
    <p class="text-[11px] text-slate-500">{{ t('offsetCamera.tuneHint') }}</p>

    <CameraPreview
      :url="config.camera_url"
      :label="t('offsetCamera.title')"
      :roi="config.roi"
      editable
      height="md"
      @update:roi="(r) => emit('update:config', { roi: r })"
    />

    <!-- Contrast convention: adapts the detector to any tip colour. -->
    <label class="block text-[11px] text-slate-400"
      >{{ t('offsetCamera.tipStyle') }}
      <select
        :value="tipStyle"
        :disabled="disabled"
        class="mt-0.5 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
        data-test="tip-style"
        @change="(e) => onTipStyle((e.target as HTMLSelectElement).value)"
      >
        <option value="dark">{{ t('offsetCamera.tipStyleDark') }}</option>
        <option value="light">{{ t('offsetCamera.tipStyleLight') }}</option>
      </select>
    </label>
    <p class="text-[10px] text-slate-500">{{ t('offsetCamera.tipStyleHint') }}</p>

    <!-- Threshold: slider for feel, number for precision. -->
    <div class="grid grid-cols-[1fr_auto] items-end gap-2">
      <label class="block text-[11px] text-slate-400"
        >{{ t('magazine.darkThreshold') }} — {{ thresholdDraft }}
        <input
          type="range"
          min="0"
          max="255"
          step="1"
          :value="thresholdDraft"
          :disabled="disabled"
          class="mt-1 w-full accent-emerald-500"
          data-test="tip-threshold-slider"
          @input="(e) => onThresholdInput((e.target as HTMLInputElement).value)"
          @change="(e) => onThresholdCommit((e.target as HTMLInputElement).value)"
        />
      </label>
      <input
        type="number"
        min="0"
        max="255"
        step="1"
        :value="thresholdDraft"
        :disabled="disabled"
        class="w-16 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
        data-test="tip-dark-threshold"
        @change="(e) => onThresholdCommit((e.target as HTMLInputElement).value)"
      />
    </div>

    <label class="block text-[11px] text-slate-400"
      >{{ t('offsetCamera.samples') }}
      <input
        type="number"
        min="1"
        max="20"
        step="1"
        :value="config.samples ?? 1"
        :disabled="disabled"
        class="mt-0.5 w-16 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
        data-test="tip-samples"
        @change="(e) => onSamples((e.target as HTMLInputElement).value)"
      />
    </label>

    <!-- Dry-run + live feedback. -->
    <div class="flex flex-wrap items-center gap-2">
      <button
        type="button"
        class="rounded border border-slate-600 px-2 py-1 text-[11px] text-slate-200 hover:bg-slate-700 disabled:opacity-50"
        :disabled="disabled || testState.busy || !config.camera_url.trim()"
        data-test="tip-test"
        @click="runTest"
      >
        {{ testState.busy ? t('magazine.measuring') : '🔍 ' + t('offsetCamera.testDetection') }}
      </button>
      <label class="flex items-center gap-1.5 text-[11px] text-slate-400">
        <input
          type="checkbox"
          :checked="autoTest"
          class="rounded border-slate-600 bg-slate-900"
          :disabled="disabled || !config.camera_url.trim()"
          data-test="tip-auto-test"
          @change="(e) => onAutoTest((e.target as HTMLInputElement).checked)"
        />
        {{ t('offsetCamera.autoTest') }}
      </label>
    </div>

    <!-- Confidence meter with the 35% trust gate marked on the bar. -->
    <div v-if="testState.confidence != null" class="space-y-0.5">
      <div class="flex items-baseline justify-between text-[10px] text-slate-400">
        <span>{{ t('offsetCamera.confidence') }}</span>
        <span data-test="tip-confidence-value">{{ confidencePct }} %</span>
      </div>
      <div
        class="relative h-2 w-full overflow-hidden rounded bg-slate-800"
        role="meter"
        :aria-valuenow="confidencePct"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-label="t('offsetCamera.confidence')"
        data-test="tip-confidence-meter"
      >
        <div
          class="h-full rounded transition-all"
          :class="meterClass"
          :style="{ width: confidencePct + '%' }"
          data-test="tip-confidence-bar"
        />
        <!-- Trust gate: results left of this line are shown but not applied. -->
        <div
          class="absolute inset-y-0 w-px bg-slate-300/70"
          :style="{ left: MIN_CONFIDENCE * 100 + '%' }"
          data-test="tip-confidence-gate"
        />
      </div>
    </div>

    <p
      v-if="testState.message"
      class="text-[11px]"
      :class="testState.ok ? 'text-emerald-400' : 'text-amber-400'"
      data-test="tip-test-msg"
    >
      {{ testState.message }}
    </p>
    <img
      v-if="testState.image"
      :src="testState.image"
      :alt="t('offsetCamera.testDetection')"
      class="max-h-40 w-auto rounded border border-slate-700"
      data-test="tip-test-preview"
    />
  </div>
</template>
