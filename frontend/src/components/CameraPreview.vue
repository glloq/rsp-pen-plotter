<script setup lang="ts">
// Reusable live camera preview: renders an MJPEG/HTTP stream (or a snapshot)
// from a URL with loading / error / empty states and a refresh button.
//
// Used by the Cameras settings tab — for each workshop camera and for the
// offset camera — so the operator can confirm a URL actually produces a feed
// before relying on it. Hardware-agnostic: a plain <img> renders an MJPEG
// stream as a live feed and a snapshot endpoint as a still.

import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    url: string
    label?: string
    // Compact height for inline previews; taller for a focused view.
    height?: 'sm' | 'md'
  }>(),
  { label: '', height: 'sm' },
)

const { t } = useI18n()

const trimmed = computed(() => props.url.trim())
const errored = ref(false)
// Cache-buster so "refresh" re-pulls a snapshot URL (and restarts a stalled
// MJPEG stream) without the operator editing the URL.
const nonce = ref(0)
const src = computed(() => {
  if (!trimmed.value) return ''
  const sep = trimmed.value.includes('?') ? '&' : '?'
  return nonce.value ? `${trimmed.value}${sep}_op=${nonce.value}` : trimmed.value
})

// A changed URL deserves a fresh attempt.
watch(trimmed, () => {
  errored.value = false
})

function refresh(): void {
  errored.value = false
  nonce.value = Date.now()
}

const heightClass = computed(() => (props.height === 'md' ? 'h-48' : 'h-28'))
</script>

<template>
  <div
    class="relative flex items-center justify-center overflow-hidden rounded border border-slate-700 bg-black"
    :class="heightClass"
    data-test="camera-preview"
  >
    <!-- Empty: no URL yet. -->
    <p
      v-if="!trimmed"
      class="px-2 text-center text-[11px] text-slate-500"
      data-test="preview-empty"
    >
      {{ t('cameraPreview.empty') }}
    </p>

    <!-- Error: the stream/snapshot failed to load. -->
    <div
      v-else-if="errored"
      class="flex flex-col items-center gap-1 px-2 text-center"
      data-test="preview-error"
    >
      <span aria-hidden="true">⚠️</span>
      <p class="text-[11px] text-red-300">{{ t('camera.streamError') }}</p>
      <button
        type="button"
        class="rounded border border-slate-600 px-2 py-0.5 text-[10px] text-slate-200 hover:bg-slate-700"
        data-test="preview-retry"
        @click="refresh"
      >
        {{ t('cameraPreview.retry') }}
      </button>
    </div>

    <!-- Live feed. -->
    <template v-else>
      <img
        :key="src"
        :src="src"
        :alt="label || t('camera.title')"
        class="max-h-full max-w-full object-contain"
        data-test="preview-img"
        @error="errored = true"
      />
      <span
        class="absolute left-1 top-1 flex items-center gap-1 rounded bg-black/50 px-1.5 py-0.5 text-[9px] font-medium text-emerald-300"
        data-test="preview-live"
      >
        <span class="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
        {{ t('camera.live') }}
      </span>
      <button
        type="button"
        class="absolute right-1 top-1 rounded bg-black/50 px-1.5 py-0.5 text-[10px] text-slate-200 hover:bg-black/70"
        :title="t('cameraPreview.refresh')"
        :aria-label="t('cameraPreview.refresh')"
        data-test="preview-refresh"
        @click="refresh"
      >
        ↻
      </button>
    </template>
  </div>
</template>
