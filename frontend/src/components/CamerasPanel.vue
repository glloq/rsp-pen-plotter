<script setup lang="ts">
// Cameras settings tab — groups every camera concern in one place:
//   1. Workshop cameras (up to two live feeds; also the timelapse source).
//   2. Offset camera (dedicated tip-offset measurement station).
//   3. Timelapse (auto-record + which workshop camera to record from).
//
// Workshop cameras are client-side preferences (ui store, localStorage); the
// offset camera lives on the machine profile. Both are optional and
// independent — see OffsetCameraSettings / TimelapseSettings.

import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useUiStore } from '../stores/ui'
import OffsetCameraSettings from './OffsetCameraSettings.vue'
import TimelapseSettings from './TimelapseSettings.vue'

const { t } = useI18n()
const ui = useUiStore()
const { cameras } = storeToRefs(ui)
</script>

<template>
  <div class="space-y-3">
    <!-- 1. Workshop cameras (live view + timelapse source). -->
    <div class="rounded-lg border border-slate-700 bg-slate-800 p-3 space-y-3 text-xs">
      <div>
        <h3 class="text-[11px] uppercase tracking-wider text-slate-500">
          {{ t('system.camera') }}
        </h3>
        <p class="mt-1 text-[11px] text-slate-500">{{ t('system.cameraHint') }}</p>
      </div>

      <div
        v-for="(cam, i) in cameras"
        :key="i"
        class="space-y-2 rounded border border-slate-700 bg-slate-900/40 p-2"
        :data-test="`camera-slot-${i}`"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="text-[11px] font-medium text-slate-300">
            {{ t('system.cameraN', { n: i + 1 })
            }}<span v-if="i > 0" class="font-normal text-slate-500">
              · {{ t('system.cameraOptional') }}</span
            >
          </span>
          <label class="flex items-center gap-1.5 text-slate-300">
            <input
              v-model="cam.enabled"
              type="checkbox"
              class="h-3.5 w-3.5 shrink-0 accent-emerald-500"
              :data-test="`camera-enable-${i}`"
            />
            <span>{{ t('system.cameraEnable') }}</span>
          </label>
        </div>
        <label class="block space-y-1">
          <span class="text-[11px] text-slate-400">{{ t('system.cameraLabel') }}</span>
          <input
            v-model="cam.label"
            type="text"
            :placeholder="t('system.cameraN', { n: i + 1 })"
            class="w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 text-[11px] text-slate-100 placeholder:text-slate-600"
            :data-test="`camera-label-${i}`"
          />
        </label>
        <label class="block space-y-1">
          <span class="text-[11px] text-slate-400">{{ t('system.cameraUrl') }}</span>
          <input
            v-model="cam.url"
            type="url"
            inputmode="url"
            :placeholder="t('system.cameraUrlPlaceholder')"
            class="w-full rounded border border-slate-600 bg-slate-900 px-2 py-1 font-mono text-[11px] text-slate-100 placeholder:text-slate-600"
            :data-test="`camera-url-${i}`"
          />
        </label>
      </div>
      <p class="text-[11px] text-slate-500">{{ t('system.cameraUrlHint') }}</p>
    </div>

    <!-- 2. Offset camera (per-machine tip-offset station). -->
    <OffsetCameraSettings />

    <!-- 3. Timelapse. -->
    <TimelapseSettings />
  </div>
</template>
