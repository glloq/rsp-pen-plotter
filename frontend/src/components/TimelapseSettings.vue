<script setup lang="ts">
// Timelapse *defaults* surfaced in the Settings modal.
//
// The recording controls (start / stop) and the saved-clip library live on
// the Plotter tab (``TimelapsePanel``). This panel only edits the persistent
// preferences — auto-record, default camera, interval, FPS — which the store
// shares with the auto-during-prints hook. Everything writes straight to the
// timelapse store, so the two surfaces stay in sync.

import { computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useTimelapseStore } from '../stores/timelapse'
import { useUiStore } from '../stores/ui'

const { t } = useI18n()
const ui = useUiStore()
const timelapse = useTimelapseStore()
const { cameras } = storeToRefs(ui)
const { autoEnabled, intervalSeconds, fps, cameraSlot } = storeToRefs(timelapse)

// Cameras available to record from (enabled + with a URL), tagged with their
// original slot index so the picker and auto-capture agree on a slot.
interface Cam {
  slot: number
  label: string
}
const activeCameras = computed<Cam[]>(() =>
  cameras.value
    .map((c, i) => ({
      slot: i,
      enabled: c.enabled,
      url: c.url.trim(),
      label: c.label.trim() || t('camera.defaultLabel', { n: i + 1 }),
    }))
    .filter((c) => c.enabled && c.url.length > 0)
    .map((c) => ({ slot: c.slot, label: c.label })),
)

// Keep the selected slot pointing at a configured camera (mirrors the
// TimelapsePanel guard so a deleted/disabled camera never strands the pick).
watch(
  activeCameras,
  (list) => {
    if (list.length && !list.some((c) => c.slot === cameraSlot.value)) {
      cameraSlot.value = list[0]!.slot
    }
  },
  { immediate: true },
)

// The camera streams are configured in the Cameras tab (above this section).
function goToCameras(): void {
  ui.settingsTab = 'cameras'
}
</script>

<template>
  <section class="space-y-4" data-test="timelapse-settings">
    <header>
      <h2 class="text-base font-semibold text-slate-100">{{ t('timelapse.settingsTitle') }}</h2>
      <p class="mt-1 text-xs text-slate-400">{{ t('timelapse.settingsHint') }}</p>
    </header>

    <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-3 text-xs">
      <!-- Auto-record applies regardless of a configured camera, but a print
           can only record once a camera exists — keep the toggle enabled so
           the preference can be set ahead of wiring a camera. -->
      <label class="flex items-start gap-2 text-slate-300">
        <input
          v-model="autoEnabled"
          type="checkbox"
          class="mt-0.5 h-3.5 w-3.5 shrink-0 accent-emerald-500"
          data-test="timelapse-settings-auto"
        />
        <span class="leading-snug">{{ t('timelapse.auto') }}</span>
      </label>

      <!-- No camera configured to record from — point at the System tab. -->
      <p
        v-if="activeCameras.length === 0"
        class="flex flex-wrap items-center gap-1 rounded border border-dashed border-slate-700 px-2 py-2 text-[11px] text-slate-500"
        data-test="timelapse-settings-no-camera"
      >
        {{ t('timelapse.noCamera') }}
        <button type="button" class="text-emerald-400 hover:text-emerald-300" @click="goToCameras">
          {{ t('camera.configure') }}
        </button>
      </p>

      <div class="grid grid-cols-2 gap-2">
        <label v-if="activeCameras.length" class="col-span-2 block space-y-1">
          <span class="text-[11px] text-slate-400">{{ t('timelapse.camera') }}</span>
          <select
            v-model="cameraSlot"
            class="w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-100"
            data-test="timelapse-settings-camera"
          >
            <option v-for="c in activeCameras" :key="c.slot" :value="c.slot">
              {{ c.label }}
            </option>
          </select>
        </label>
        <label class="block space-y-1">
          <span class="text-[11px] text-slate-400">{{ t('timelapse.interval') }}</span>
          <input
            v-model.number="intervalSeconds"
            type="number"
            min="0.5"
            max="3600"
            step="0.5"
            class="w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-100"
            data-test="timelapse-settings-interval"
          />
        </label>
        <label class="block space-y-1">
          <span class="text-[11px] text-slate-400">{{ t('timelapse.fps') }}</span>
          <input
            v-model.number="fps"
            type="number"
            min="1"
            max="60"
            step="1"
            class="w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-xs text-slate-100"
            data-test="timelapse-settings-fps"
          />
        </label>
      </div>
    </div>
  </section>
</template>
