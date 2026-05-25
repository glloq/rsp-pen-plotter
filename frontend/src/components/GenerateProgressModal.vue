<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useUiStore } from '../stores/ui'

// Progress modal for the optimize → preflight → generate pipeline. The
// state machine lives in ui.gcodeJobState; this component only renders
// it and routes the Cancel / Close buttons back into the store. Modelled
// on UpdateProgressModal so the visual language stays consistent.

const { t } = useI18n()
const ui = useUiStore()
const { gcodeJobState } = storeToRefs(ui)

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
  () => gcodeJobState.value.phase,
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
  const start = gcodeJobState.value.startedAt
  if (!start) return 0
  return Math.max(0, Math.floor((now.value - start) / 1000))
})

const visible = computed(() => gcodeJobState.value.phase !== 'idle')

// Steps shown as a 3-row checklist so the operator can see which stage
// is current. The order matches the pipeline in job.generate().
const steps = computed(() => {
  const current = gcodeJobState.value.step
  const phase = gcodeJobState.value.phase
  const order = ['optimize', 'preflight', 'generate'] as const
  const currentIndex = current ? order.indexOf(current) : -1
  return order.map((step, index) => {
    let status: 'pending' | 'active' | 'done' | 'failed' = 'pending'
    if (phase === 'success') status = 'done'
    else if (phase === 'error' && index === currentIndex) status = 'failed'
    else if (phase === 'error' && index < currentIndex) status = 'done'
    else if (phase === 'cancelled' && index === currentIndex) status = 'failed'
    else if (phase === 'cancelled' && index < currentIndex) status = 'done'
    else if (phase === 'running') {
      if (index < currentIndex) status = 'done'
      else if (index === currentIndex) status = 'active'
    }
    return { key: step, status, label: t(`gcodeJob.step.${step}`) }
  })
})

function cancel(): void {
  ui.cancelGcodeJob()
}

function close(): void {
  ui.dismissGcodeJob()
}
</script>

<template>
  <div
    v-if="visible"
    class="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/80 backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
    aria-labelledby="gcode-modal-title"
  >
    <div
      class="w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-2xl"
      @click.stop
    >
      <div class="flex items-start gap-3">
        <span
          v-if="gcodeJobState.phase === 'running'"
          class="mt-1 inline-block h-5 w-5 shrink-0 animate-spin rounded-full border-2 border-slate-600 border-t-emerald-400"
          aria-hidden="true"
        />
        <span
          v-else-if="gcodeJobState.phase === 'success'"
          class="mt-0.5 text-2xl leading-none text-emerald-400"
          aria-hidden="true"
          >✓</span
        >
        <span
          v-else-if="gcodeJobState.phase === 'cancelled'"
          class="mt-0.5 text-2xl leading-none text-amber-300"
          aria-hidden="true"
          >⊘</span
        >
        <span v-else class="mt-0.5 text-2xl leading-none text-red-400" aria-hidden="true">✕</span>

        <div class="min-w-0 flex-1">
          <h2 id="gcode-modal-title" class="text-base font-semibold text-slate-100">
            <template v-if="gcodeJobState.phase === 'running'">{{
              t('gcodeJob.titleRunning')
            }}</template>
            <template v-else-if="gcodeJobState.phase === 'success'">{{
              t('gcodeJob.titleSuccess')
            }}</template>
            <template v-else-if="gcodeJobState.phase === 'cancelled'">{{
              t('gcodeJob.titleCancelled')
            }}</template>
            <template v-else>{{ t('gcodeJob.titleError') }}</template>
          </h2>
          <p class="mt-1 text-sm text-slate-300">
            {{ gcodeJobState.message }}
          </p>
          <p v-if="gcodeJobState.phase === 'running'" class="mt-2 font-mono text-xs text-slate-500">
            {{ t('gcodeJob.elapsed', { seconds: elapsedSeconds }) }}
          </p>
        </div>
      </div>

      <ul class="mt-4 space-y-1.5 text-sm">
        <li
          v-for="step in steps"
          :key="step.key"
          class="flex items-center gap-2"
          :class="{
            'text-slate-500': step.status === 'pending',
            'text-emerald-300': step.status === 'done',
            'text-sky-200': step.status === 'active',
            'text-red-300': step.status === 'failed',
          }"
        >
          <span class="inline-flex h-5 w-5 shrink-0 items-center justify-center" aria-hidden="true">
            <span v-if="step.status === 'done'" class="text-emerald-400">✓</span>
            <span
              v-else-if="step.status === 'active'"
              class="inline-block h-3 w-3 animate-spin rounded-full border-2 border-slate-600 border-t-sky-300"
            />
            <span v-else-if="step.status === 'failed'" class="text-red-400">✕</span>
            <span v-else class="text-slate-600">○</span>
          </span>
          <span>{{ step.label }}</span>
        </li>
      </ul>

      <div
        v-if="gcodeJobState.phase === 'error' && gcodeJobState.error"
        class="mt-4 max-h-40 overflow-auto rounded border border-red-700/60 bg-red-950/40 px-3 py-2 font-mono text-[11px] text-red-200 whitespace-pre-wrap"
      >
        {{ gcodeJobState.error }}
      </div>

      <div class="mt-5 flex justify-end gap-2">
        <button
          v-if="gcodeJobState.phase === 'running'"
          type="button"
          class="rounded border border-amber-700 bg-amber-900/40 px-3 py-1.5 text-sm text-amber-100 hover:bg-amber-900/60"
          @click="cancel"
        >
          {{ t('gcodeJob.cancel') }}
        </button>
        <button
          v-else
          type="button"
          class="rounded border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          @click="close"
        >
          {{ t('gcodeJob.close') }}
        </button>
      </div>
    </div>
  </div>
</template>
