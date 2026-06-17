<script setup lang="ts">
// Workshop camera feed for the Plotter tab.
//
// Sits above the manual cockpit so the operator can watch the bed while
// jogging. Each camera is an MJPEG/HTTP stream URL (configured in System
// settings) — hardware-agnostic: USB (mjpg-streamer / ustreamer), Pi CSI
// (ustreamer / libcamera) or an IP camera all expose one, which a plain
// <img> renders as a live feed. Up to two cameras; when more than one is
// active a switcher picks which to view. When none is configured the slot
// stays visible as a hint that links into the settings panel.

import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useInViewport } from '../composables/useInViewport'
import { useUiStore, type CameraConfig } from '../stores/ui'

const { t } = useI18n()
const ui = useUiStore()
const { cameras } = storeToRefs(ui)

// Enabled cameras that have a URL, each tagged with its original slot
// index so the default "Camera N" label stays stable when slot 1 is off.
interface ActiveCamera extends CameraConfig {
  index: number
}
const activeCameras = computed<ActiveCamera[]>(() =>
  cameras.value
    .map((c, index) => ({ ...c, index }))
    .filter((c) => c.enabled && c.url.trim().length > 0),
)
const active = computed(() => activeCameras.value.length > 0)

// Which active camera is shown. Clamp when the active set shrinks.
const selected = ref(0)
watch(activeCameras, (list) => {
  if (selected.value >= list.length) selected.value = 0
})
const current = computed<ActiveCamera | null>(() => activeCameras.value[selected.value] ?? null)
const streamSrc = computed(() => current.value?.url.trim() ?? '')

function cameraLabel(cam: ActiveCamera): string {
  return cam.label.trim() || t('camera.defaultLabel', { n: cam.index + 1 })
}

// Only hold the (long-lived) MJPEG connection open while the panel is
// actually on screen. The Plotter tab is kept mounted via ``v-show``, so
// without this the <img> would keep pulling + decoding frames on every
// other tab. IntersectionObserver flips this both ways; it degrades to
// always-visible where the observer is unavailable (tests / old browsers).
const root = ref<HTMLElement | null>(null)
const visible = useInViewport(root, { once: false })

// Track load failures so a dead stream shows an error rather than a
// broken-image icon. Reset whenever the shown source changes so a
// corrected URL (or a switch) gets a fresh attempt.
const errored = ref(false)
watch([selected, streamSrc], () => {
  errored.value = false
})
</script>

<template>
  <section
    ref="root"
    class="flex min-h-0 flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-900"
    data-test="camera-view"
  >
    <header class="flex shrink-0 items-center gap-2 border-b border-slate-700 px-3 py-1.5">
      <span class="text-[11px] font-semibold uppercase tracking-wider text-slate-300">{{
        t('camera.title')
      }}</span>

      <!-- Switcher — only when more than one camera is active. -->
      <div
        v-if="activeCameras.length > 1"
        class="flex items-center gap-1"
        data-test="camera-switcher"
      >
        <button
          v-for="(cam, i) in activeCameras"
          :key="cam.index"
          type="button"
          class="rounded px-1.5 py-0.5 text-[10px] transition"
          :class="selected === i ? 'bg-slate-700 text-white' : 'text-slate-400 hover:bg-slate-800'"
          :data-test="`camera-select-${i}`"
          @click="selected = i"
        >
          {{ cameraLabel(cam) }}
        </button>
      </div>

      <span
        v-if="active && !errored"
        class="ml-auto flex items-center gap-1 text-[10px] font-medium text-emerald-300"
        data-test="camera-live"
      >
        <span class="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
        {{ t('camera.live') }}
      </span>
    </header>

    <!-- Live feed — fills the remaining height; only mounted while on
         screen so the stream is torn down on other tabs. ``:key`` forces a
         fresh <img> on a switch. -->
    <div v-if="active" class="flex min-h-0 flex-1 items-center justify-center bg-black">
      <img
        v-if="!errored && visible"
        :key="streamSrc"
        :src="streamSrc"
        :alt="current ? cameraLabel(current) : t('camera.title')"
        class="max-h-full max-w-full object-contain"
        data-test="camera-stream"
        @error="errored = true"
      />
      <div v-else-if="errored" class="flex flex-col items-center gap-1 px-3 text-center">
        <p class="text-xs text-red-300">{{ t('camera.streamError') }}</p>
        <p class="font-mono text-[10px] break-all text-slate-500">{{ streamSrc }}</p>
      </div>
    </div>

    <!-- Not configured: invite the operator into System settings. -->
    <button
      v-else
      type="button"
      class="flex min-h-0 flex-1 flex-col items-center justify-center gap-1 px-3 py-8 text-center hover:bg-slate-800/60"
      data-test="camera-configure"
      @click="ui.openSettings('system')"
    >
      <span aria-hidden="true" class="text-3xl">📷</span>
      <span class="text-xs text-slate-400">{{ t('camera.notConfigured') }}</span>
      <span class="text-[11px] text-sky-400">{{ t('camera.configure') }}</span>
    </button>
  </section>
</template>
