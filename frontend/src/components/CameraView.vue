<script setup lang="ts">
// Workshop camera feed for the Plotter tab.
//
// Sits above the manual cockpit so the operator can watch the bed while
// jogging. The stream is whatever URL was configured in System settings
// — typically an MJPEG endpoint from a Raspberry Pi camera
// (mjpg-streamer / motion), which a plain <img> renders as a live feed.
// When no camera is configured the slot stays visible as a hint that
// links straight into the settings panel.

import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useUiStore } from '../stores/ui'

const { t } = useI18n()
const ui = useUiStore()
const { cameraEnabled, cameraUrl } = storeToRefs(ui)

const active = computed(() => cameraEnabled.value && cameraUrl.value.trim().length > 0)

// Track load failures so a dead stream shows an error rather than a
// broken-image icon. Reset whenever the source or enabled flag changes
// so a corrected URL gets a fresh attempt.
const errored = ref(false)
watch([cameraEnabled, cameraUrl], () => {
  errored.value = false
})
</script>

<template>
  <section
    class="shrink-0 overflow-hidden rounded-lg border border-slate-700 bg-slate-900"
    data-test="camera-view"
  >
    <header class="flex items-center gap-2 border-b border-slate-700 px-3 py-1.5">
      <span class="text-[11px] uppercase tracking-wider text-slate-400">{{
        t('camera.title')
      }}</span>
      <span
        v-if="active && !errored"
        class="flex items-center gap-1 text-[10px] font-medium text-emerald-300"
        data-test="camera-live"
      >
        <span class="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
        {{ t('camera.live') }}
      </span>
    </header>

    <!-- Live feed. -->
    <div v-if="active" class="flex items-center justify-center bg-black">
      <img
        v-if="!errored"
        :src="cameraUrl"
        :alt="t('camera.title')"
        class="max-h-56 w-full object-contain"
        data-test="camera-stream"
        @error="errored = true"
      />
      <div v-else class="flex w-full flex-col items-center gap-1 px-3 py-6 text-center">
        <p class="text-xs text-red-300">{{ t('camera.streamError') }}</p>
        <p class="font-mono text-[10px] break-all text-slate-500">{{ cameraUrl }}</p>
      </div>
    </div>

    <!-- Not configured: invite the operator into System settings. -->
    <button
      v-else
      type="button"
      class="flex w-full flex-col items-center gap-1 px-3 py-6 text-center hover:bg-slate-800/60"
      data-test="camera-configure"
      @click="ui.openSettings('system')"
    >
      <span aria-hidden="true" class="text-2xl">📷</span>
      <span class="text-xs text-slate-400">{{ t('camera.notConfigured') }}</span>
      <span class="text-[11px] text-sky-400">{{ t('camera.configure') }}</span>
    </button>
  </section>
</template>
