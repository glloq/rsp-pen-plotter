<script setup lang="ts">
// Timelapse controls for the Plotter tab — collapsed by default.
//
// Captures frames from a configured camera (the chosen camera's stream
// URL is handed to the backend, which does the grabbing) and, on stop,
// assembles a downloadable MP4. Below the controls is the library of
// saved timelapses with download / delete.

import { computed, onUnmounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import type { TimelapseSummary } from '../api/client'
import { confirmAction } from '../composables/confirm'
import { resolveCameraUrl } from '../composables/useTimelapseAutoCapture'
import { useTimelapseStore } from '../stores/timelapse'
import { useUiStore } from '../stores/ui'

const { t } = useI18n()
const ui = useUiStore()
const timelapse = useTimelapseStore()
const { cameras } = storeToRefs(ui)
// Capture settings (interval / fps / camera slot / auto) live in the store
// so the auto-during-prints hook shares them.
const { status, files, busy, autoEnabled, intervalSeconds, fps, cameraSlot } =
  storeToRefs(timelapse)

// Cameras available to record from (enabled + with a URL), tagged with
// their original slot index so the picker and auto-capture agree.
interface Cam {
  slot: number
  url: string
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
    .map((c) => ({ slot: c.slot, url: c.url, label: c.label })),
)

// Keep the selected slot pointing at a configured camera.
watch(
  activeCameras,
  (list) => {
    if (list.length && !list.some((c) => c.slot === cameraSlot.value)) {
      cameraSlot.value = list[0]!.slot
    }
  },
  { immediate: true },
)

const canStart = computed(
  () => activeCameras.value.length > 0 && !status.value.recording && !busy.value,
)

async function start(): Promise<void> {
  const url = resolveCameraUrl(cameras.value, cameraSlot.value)
  if (!url) return
  // Manual recordings auto-name from their date in the list; auto-record
  // names from the job. So no label field is needed in this condensed UI.
  await timelapse.start(url, intervalSeconds.value, fps.value, '')
}

async function stop(): Promise<void> {
  await timelapse.stop()
}

async function remove(file: TimelapseSummary): Promise<void> {
  const ok = await confirmAction({
    title: t('timelapse.deleteTitle'),
    message: t('timelapse.deleteMsg', { name: file.label || file.id }),
    confirmLabel: t('timelapse.delete'),
    cancelLabel: t('confirm.cancel'),
    danger: true,
  })
  if (ok) await timelapse.remove(file.id)
}

// The panel is always visible in its column, so poll the recorder status
// (and refresh the saved list on entry) only while the Plotter tab is the
// active canvas tab — it's display:none on the others.
let pollTimer: ReturnType<typeof setInterval> | null = null
const shouldPoll = computed(() => ui.canvasTab === 'plotter')
watch(
  shouldPoll,
  (poll) => {
    if (poll) {
      void timelapse.refreshStatus()
      void timelapse.refreshList()
      pollTimer = setInterval(() => void timelapse.refreshStatus(), 1500)
    } else if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  },
  { immediate: true },
)
onUnmounted(() => {
  if (pollTimer !== null) clearInterval(pollTimer)
})

function formatSize(bytes: number): string {
  if (bytes <= 0) return '—'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} ko`
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`
}
function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}
</script>

<template>
  <section
    class="flex min-h-0 flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-900"
    data-test="timelapse-panel"
  >
    <header
      class="flex shrink-0 items-center justify-between gap-2 border-b border-slate-700 px-3 py-1.5"
    >
      <span class="text-[11px] font-semibold uppercase tracking-wider text-slate-300">
        🎬 {{ t('timelapse.title') }}
      </span>
      <span
        v-if="status.recording"
        class="flex items-center gap-1 text-[10px] font-medium text-red-300"
        data-test="timelapse-rec"
      >
        <span class="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
        {{ t('timelapse.recording') }} · {{ status.frame_count }}
      </span>
    </header>

    <div
      class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-2.5"
      data-test="timelapse-body"
    >
      <!-- No camera configured to record from. -->
      <p
        v-if="activeCameras.length === 0"
        class="rounded border border-dashed border-slate-700 px-2 py-3 text-center text-[11px] leading-snug text-slate-500"
        data-test="timelapse-no-camera"
      >
        {{ t('timelapse.noCamera') }}
      </p>

      <template v-else>
        <!-- Auto-record for the duration of every print. -->
        <label
          class="flex items-center gap-2 rounded bg-slate-800/60 px-2 py-1.5 text-[11px] text-slate-300"
        >
          <input
            v-model="autoEnabled"
            type="checkbox"
            class="h-3.5 w-3.5 shrink-0 accent-emerald-500"
            data-test="timelapse-auto"
          />
          <span class="leading-snug">{{ t('timelapse.auto') }}</span>
        </label>

        <!-- Recording: live state + stop. -->
        <div
          v-if="status.recording"
          class="flex items-center justify-between gap-2 rounded border border-red-800 bg-red-950/30 px-2 py-2"
        >
          <span class="text-[11px] text-red-200">
            {{ status.frame_count }} {{ t('timelapse.frames') }}
          </span>
          <button
            type="button"
            class="rounded bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-500 disabled:opacity-50"
            :disabled="busy"
            data-test="timelapse-stop"
            @click="stop"
          >
            ⏹ {{ t('timelapse.stop') }}
          </button>
        </div>

        <!-- Idle: capture controls. -->
        <div v-else class="space-y-2">
          <label v-if="activeCameras.length > 1" class="block space-y-1">
            <span class="text-[10px] uppercase tracking-wider text-slate-500">{{
              t('timelapse.camera')
            }}</span>
            <select
              v-model="cameraSlot"
              class="w-full rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-slate-100"
              data-test="timelapse-camera"
            >
              <option v-for="c in activeCameras" :key="c.slot" :value="c.slot">
                {{ c.label }}
              </option>
            </select>
          </label>
          <div class="grid grid-cols-2 gap-2">
            <label class="block space-y-1">
              <span class="text-[10px] uppercase tracking-wider text-slate-500">{{
                t('timelapse.interval')
              }}</span>
              <input
                v-model.number="intervalSeconds"
                type="number"
                min="0.5"
                max="3600"
                step="0.5"
                class="w-full rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                data-test="timelapse-interval"
              />
            </label>
            <label class="block space-y-1">
              <span class="text-[10px] uppercase tracking-wider text-slate-500">{{
                t('timelapse.fps')
              }}</span>
              <input
                v-model.number="fps"
                type="number"
                min="1"
                max="60"
                step="1"
                class="w-full rounded border border-slate-600 bg-slate-950 px-2 py-1 text-xs text-slate-100"
                data-test="timelapse-fps"
              />
            </label>
          </div>
          <button
            type="button"
            class="w-full rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
            :disabled="!canStart"
            data-test="timelapse-start"
            @click="start"
          >
            ⏺ {{ t('timelapse.start') }}
          </button>
        </div>
      </template>

      <!-- Saved timelapses. -->
      <div class="mt-1 border-t border-slate-800 pt-2">
        <ul v-if="files.length" class="space-y-1" data-test="timelapse-list">
          <li
            v-for="file in files"
            :key="file.id"
            class="rounded border border-slate-700 bg-slate-800/60 px-2 py-1.5"
            :data-test="`timelapse-file-${file.id}`"
          >
            <div class="flex items-center gap-1.5">
              <div class="min-w-0 flex-1">
                <span class="block truncate text-xs font-medium text-slate-200">{{
                  file.label || formatDate(file.created_at)
                }}</span>
                <span class="text-[10px] text-slate-500">
                  {{ file.frame_count }} {{ t('timelapse.frames') }} · {{ file.duration_seconds }}s
                  · {{ formatSize(file.size_bytes) }}
                </span>
              </div>
              <button
                type="button"
                class="shrink-0 rounded px-1.5 py-0.5 text-xs text-sky-300 hover:bg-slate-700 disabled:opacity-30"
                :disabled="!file.has_video"
                :title="t('timelapse.download')"
                :data-test="`timelapse-download-${file.id}`"
                @click="timelapse.download(file)"
              >
                ⬇
              </button>
              <button
                type="button"
                class="shrink-0 rounded px-1.5 py-0.5 text-xs text-red-300 hover:bg-red-900/40"
                :title="t('timelapse.delete')"
                :data-test="`timelapse-delete-${file.id}`"
                @click="remove(file)"
              >
                🗑
              </button>
            </div>
          </li>
        </ul>
        <p v-else class="text-center text-[11px] text-slate-500">{{ t('timelapse.empty') }}</p>
      </div>

      <p v-if="timelapse.error" class="text-[10px] text-red-400">{{ timelapse.error }}</p>
    </div>
  </section>
</template>
