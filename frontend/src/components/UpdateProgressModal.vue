<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useUiStore } from '../stores/ui'

const { t } = useI18n()
const ui = useUiStore()
const { updateState } = storeToRefs(ui)

// Live elapsed-time counter — the backend doesn't stream progress, so an
// elapsed timer is the cheapest way to reassure the operator that the
// request is still in flight (vs hung).
const now = ref(Date.now())
let tick: ReturnType<typeof setInterval> | null = null

function startTicker(): void {
  if (tick) return
  tick = setInterval(() => {
    now.value = Date.now()
  }, 1000)
}

function stopTicker(): void {
  if (tick) {
    clearInterval(tick)
    tick = null
  }
}

watch(
  () => updateState.value.phase,
  (phase) => {
    if (phase === 'running') {
      now.value = Date.now()
      startTicker()
    } else {
      stopTicker()
    }
  },
  { immediate: true },
)

onBeforeUnmount(stopTicker)

const elapsedSeconds = computed(() => {
  const start = updateState.value.startedAt
  if (!start) return 0
  return Math.max(0, Math.floor((now.value - start) / 1000))
})

const visible = computed(() => updateState.value.phase !== 'idle')

function reload(): void {
  // Hard reload: bypasses the disk cache so the freshly-built bundle is
  // fetched. Pairs with the Ctrl+Shift+R reminder for users who'd rather
  // click than memorise the shortcut.
  window.location.reload()
}

function dismiss(): void {
  ui.dismissUpdate()
}
</script>

<template>
  <div
    v-if="visible"
    class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
    :aria-labelledby="'update-modal-title'"
  >
    <div
      class="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-2xl"
      @click.stop
    >
      <div class="flex items-start gap-3">
        <span
          v-if="updateState.phase === 'running'"
          class="mt-1 inline-block h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-slate-600 border-t-emerald-400"
          aria-hidden="true"
        />
        <span
          v-else-if="updateState.phase === 'success'"
          class="mt-0.5 text-2xl leading-none text-emerald-400"
          aria-hidden="true"
        >✓</span>
        <span
          v-else-if="updateState.phase === 'noop'"
          class="mt-0.5 text-2xl leading-none text-sky-300"
          aria-hidden="true"
        >ℹ</span>
        <span
          v-else
          class="mt-0.5 text-2xl leading-none text-red-400"
          aria-hidden="true"
        >✕</span>

        <div class="min-w-0 flex-1">
          <h2 id="update-modal-title" class="text-base font-semibold text-slate-100">
            <template v-if="updateState.phase === 'running'">{{ t('updateModal.titleRunning') }}</template>
            <template v-else-if="updateState.phase === 'success'">{{ t('updateModal.titleSuccess') }}</template>
            <template v-else-if="updateState.phase === 'noop'">{{ t('updateModal.titleNoop') }}</template>
            <template v-else>{{ t('updateModal.titleError') }}</template>
          </h2>
          <p class="mt-1 text-sm text-slate-300">
            {{ updateState.message }}
          </p>
          <p
            v-if="updateState.phase === 'running'"
            class="mt-2 font-mono text-xs text-slate-500"
          >
            {{ t('updateModal.elapsed', { seconds: elapsedSeconds }) }}
          </p>
        </div>
      </div>

      <div
        v-if="updateState.phase === 'running'"
        class="mt-4 rounded border border-amber-700/60 bg-amber-950/40 px-3 py-2 text-xs text-amber-200"
      >
        ⚠ {{ t('updateModal.doNotClose') }}
      </div>

      <div
        v-if="updateState.phase === 'success' && updateState.forced"
        class="mt-4 rounded border border-amber-700/60 bg-amber-950/40 px-3 py-2 text-xs text-amber-200"
      >
        ⚠ {{ t('updateModal.forcedNotice') }}
      </div>

      <div
        v-if="updateState.phase === 'success' && updateState.newCommitApplied"
        class="mt-4 space-y-2 rounded border border-emerald-700/60 bg-emerald-950/40 px-3 py-2 text-xs text-emerald-100"
      >
        <p class="font-semibold">{{ t('updateModal.cacheTitle') }}</p>
        <p>{{ t('updateModal.cacheHint') }}</p>
        <p class="font-mono text-[11px] text-emerald-200">
          {{ t('updateModal.cacheShortcut') }}
        </p>
      </div>

      <div
        v-if="updateState.phase === 'error' && updateState.error"
        class="mt-4 max-h-40 overflow-auto rounded border border-red-700/60 bg-red-950/40 px-3 py-2 font-mono text-[11px] text-red-200 whitespace-pre-wrap"
      >
        {{ updateState.error }}
      </div>

      <div v-if="updateState.phase !== 'running'" class="mt-5 flex justify-end gap-2">
        <button
          v-if="updateState.phase === 'success' && updateState.newCommitApplied"
          type="button"
          class="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500"
          @click="reload"
        >
          {{ t('updateModal.reloadNow') }}
        </button>
        <button
          type="button"
          class="rounded border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          @click="dismiss"
        >
          {{ t('updateModal.close') }}
        </button>
      </div>
    </div>
  </div>
</template>
