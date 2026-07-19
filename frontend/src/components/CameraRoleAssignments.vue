<script setup lang="ts">
// Camera role assignment — one glance, one click (operator request):
// « quelle caméra filme la timelapse, laquelle mesure l'offset ? »
//
// The two roles already had storage, but scattered across surfaces:
// the timelapse records from ``timelapse.cameraSlot`` (picked deep in
// the Timelapse section) and the offset station reads the machine
// profile's ``tip_calibration.camera_url`` (picked inside the Offset
// section). This panel is a thin assignment matrix over those SAME
// storages — no third source of truth, so the detailed sections and
// this summary can never disagree:
//
//   - Timelapse role  → writes ``timelapse.cameraSlot`` (ui store slot).
//   - Offset role     → writes ``tip_calibration.camera_url`` on the
//     selected machine profile (creating the block with defaults when
//     the station wasn't enabled yet, same as OffsetCameraSettings).
//
// One camera can hold BOTH roles (single-USB-camera setup); with two
// cameras each role gets its own. The offset select shows « URL
// personnalisée » when the profile's URL matches no configured camera
// (typed by hand in the Offset section) instead of silently rewriting it.

import { computed, ref, toRaw } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import type { MachineProfile, TipCalibrationConfig } from '../api/client'
import { useJobStore } from '../stores/job'
import { useTimelapseStore } from '../stores/timelapse'
import { useUiStore } from '../stores/ui'

const { t } = useI18n()
const ui = useUiStore()
const job = useJobStore()
const timelapse = useTimelapseStore()
const { cameras } = storeToRefs(ui)
const { cameraSlot } = storeToRefs(timelapse)

interface CameraOption {
  slot: number
  label: string
  url: string
}

// Only enabled cameras with a stream URL are assignable.
const options = computed<CameraOption[]>(() =>
  cameras.value
    .map((c, i) => ({
      slot: i,
      label: c.label.trim() || t('system.cameraN', { n: i + 1 }),
      url: c.url.trim(),
    }))
    .filter((c) => c.url.length > 0 && cameras.value[c.slot]?.enabled),
)

const profile = computed(() => job.selectedProfile ?? null)
const tipConfig = computed<TipCalibrationConfig | null>(
  () => profile.value?.tip_calibration ?? null,
)

// ---- Offset role: which slot matches the profile's camera URL? ----
const OFFSET_CUSTOM = 'custom'
const OFFSET_NONE = ''

const offsetSelection = computed<string>(() => {
  const url = tipConfig.value?.camera_url.trim() ?? ''
  if (!url) return OFFSET_NONE
  const match = options.value.find((c) => c.url === url)
  return match ? String(match.slot) : OFFSET_CUSTOM
})

const saving = ref(false)
const saveError = ref<string | null>(null)

// Same default block OffsetCameraSettings creates when the station is
// first enabled — assigning a camera from here must not silently ship
// a half-formed config.
function defaultTipConfig(): TipCalibrationConfig {
  return {
    camera_url: '',
    station_position: null,
    reference_slot: 0,
    mm_per_pixel: 0.1,
    scale_source: 'unset',
    detector: 'dark_blob',
    tip_style: 'dark',
    dark_threshold: 80,
    samples: 1,
    roi: null,
  }
}

async function assignOffset(value: string): Promise<void> {
  if (value === OFFSET_CUSTOM || saving.value) return
  const current = profile.value
  if (!current) return
  const chosen = value === OFFSET_NONE ? null : options.value.find((c) => String(c.slot) === value)
  if (value !== OFFSET_NONE && !chosen) return
  saving.value = true
  saveError.value = null
  try {
    const next: MachineProfile = structuredClone(toRaw(current))
    if (chosen) {
      next.tip_calibration = {
        ...(next.tip_calibration ?? defaultTipConfig()),
        camera_url: chosen.url,
      }
    } else if (next.tip_calibration) {
      // « — » clears the camera but keeps the rest of the station
      // config (scale, ROI…) so re-assigning later loses nothing.
      next.tip_calibration = { ...next.tip_calibration, camera_url: '' }
    }
    await job.saveProfile(next)
  } catch (err) {
    saveError.value =
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      t('profile.saveFailed')
  } finally {
    saving.value = false
  }
}

// Roles held by a camera slot, for the per-camera badges.
function rolesOf(slot: number): string[] {
  const roles: string[] = []
  if (options.value.some((c) => c.slot === slot) && cameraSlot.value === slot) {
    roles.push(t('cameraRoles.timelapse'))
  }
  if (offsetSelection.value === String(slot)) roles.push(t('cameraRoles.offset'))
  return roles
}

defineExpose({ rolesOf })
</script>

<template>
  <div
    class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-3 text-xs"
    data-test="camera-roles"
  >
    <div>
      <h3 class="text-[11px] uppercase tracking-wider text-slate-500">
        {{ t('cameraRoles.title') }}
      </h3>
      <p class="mt-1 text-[11px] text-slate-500">{{ t('cameraRoles.hint') }}</p>
    </div>

    <p v-if="!options.length" class="text-[11px] text-amber-300" data-test="camera-roles-empty">
      {{ t('cameraRoles.noCameras') }}
    </p>

    <template v-else>
      <!-- Timelapse role — writes the timelapse store's slot. -->
      <label class="flex items-center justify-between gap-2">
        <span class="flex items-center gap-1.5 text-slate-300">
          <span aria-hidden="true">🎬</span>
          {{ t('cameraRoles.timelapse') }}
        </span>
        <select
          v-model.number="cameraSlot"
          class="w-44 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-[11px] text-slate-100"
          data-test="camera-role-timelapse"
        >
          <option v-for="c in options" :key="c.slot" :value="c.slot">{{ c.label }}</option>
        </select>
      </label>

      <!-- Offset role — writes the machine profile's tip camera URL. -->
      <label class="flex items-center justify-between gap-2">
        <span class="flex items-center gap-1.5 text-slate-300">
          <span aria-hidden="true">🎯</span>
          {{ t('cameraRoles.offset') }}
        </span>
        <select
          :value="offsetSelection"
          :disabled="!profile || saving"
          class="w-44 rounded border border-slate-600 bg-slate-900 px-2 py-1 text-[11px] text-slate-100 disabled:opacity-50"
          data-test="camera-role-offset"
          @change="(e) => assignOffset((e.target as HTMLSelectElement).value)"
        >
          <option value="">—</option>
          <option v-for="c in options" :key="c.slot" :value="String(c.slot)">
            {{ c.label }}
          </option>
          <option v-if="offsetSelection === 'custom'" value="custom" disabled>
            {{ t('cameraRoles.customUrl') }}
          </option>
        </select>
      </label>
      <p v-if="!profile" class="text-[11px] text-slate-500">
        {{ t('cameraRoles.needsProfile') }}
      </p>
      <p
        v-else-if="offsetSelection === 'custom'"
        class="text-[11px] text-slate-500"
        data-test="camera-role-offset-custom"
      >
        {{ t('cameraRoles.customUrlHint') }}
      </p>
      <p v-if="saveError" class="text-[11px] text-red-400">{{ saveError }}</p>

      <!-- At-a-glance summary: one line per configured camera with its
           role badges — the answer to « laquelle fait quoi ? ». -->
      <ul class="space-y-1" data-test="camera-roles-summary">
        <li
          v-for="c in options"
          :key="c.slot"
          class="flex items-center justify-between gap-2 rounded border border-slate-700/60 bg-slate-900/40 px-2 py-1"
        >
          <span class="truncate text-slate-300">{{ c.label }}</span>
          <span class="flex shrink-0 gap-1">
            <span
              v-for="role in rolesOf(c.slot)"
              :key="role"
              class="rounded bg-emerald-900/50 px-1.5 py-0.5 text-[10px] text-emerald-200"
            >
              {{ role }}
            </span>
            <span v-if="!rolesOf(c.slot).length" class="text-[10px] text-slate-600">
              {{ t('cameraRoles.unassigned') }}
            </span>
          </span>
        </li>
      </ul>
    </template>
  </div>
</template>
