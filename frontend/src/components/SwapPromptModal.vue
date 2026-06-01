<script setup lang="ts">
// Swap-prompt modal — surfaces a pen/colour change the running job is
// halted on.
//
// When a queued run reaches a guided tool change (manual swap, or a
// magazine load for a colour that isn't mounted), the backend parks the
// head at the pen-change position and reflects the run as ``paused`` with
// a ``swap_prompt`` describing what to do. This modal makes that
// impossible to miss: it overlays the whole app with the instruction and
// a single big "I changed the pen — Resume" action, plus an escape hatch
// to cancel the run. Resuming routes back through the queue store, which
// tells the controller to continue streaming from the swap boundary.
//
// Purely presentational against the queue store: it reads the active run
// and emits the lifecycle action; the store owns the API call.

import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQueueStore } from '../stores/queue'

const { t } = useI18n()
const queue = useQueueStore()

// Show only when the live run is paused *for a swap* (a plain operator
// pause carries no ``swap_prompt`` and must not pop this modal).
const run = computed(() => queue.active[0] ?? null)
const visible = computed(() => run.value?.state === 'paused' && Boolean(run.value?.swap_prompt))

async function resume(): Promise<void> {
  if (run.value) await queue.act(run.value.id, 'resume')
}

async function cancel(): Promise<void> {
  if (run.value) await queue.act(run.value.id, 'cancel')
}
</script>

<template>
  <div
    v-if="visible && run"
    class="fixed inset-0 z-[10050] flex items-center justify-center bg-black/70 p-4"
    role="alertdialog"
    aria-modal="true"
    :aria-label="t('swap.title')"
    data-test="swap-prompt-modal"
  >
    <div
      class="w-full max-w-md rounded-xl border border-amber-600/60 bg-slate-900 p-6 text-center shadow-2xl"
    >
      <div
        class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-amber-500/20 text-2xl"
      >
        ✋
      </div>
      <h2 class="text-lg font-semibold text-amber-200">{{ t('swap.title') }}</h2>
      <p class="mt-1 text-xs uppercase tracking-wider text-slate-500">{{ run.name }}</p>

      <p
        class="mt-4 rounded-lg bg-slate-800 px-4 py-3 text-sm text-slate-100"
        data-test="swap-prompt-text"
      >
        {{ run.swap_prompt }}
      </p>

      <p class="mt-3 text-[11px] text-slate-400">{{ t('swap.parkedHint') }}</p>

      <div class="mt-5 flex flex-col gap-2">
        <button
          type="button"
          class="w-full rounded-lg bg-emerald-600 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-500"
          data-test="swap-resume"
          @click="resume"
        >
          ▶ {{ t('swap.resume') }}
        </button>
        <button
          type="button"
          class="w-full rounded-lg border border-red-900/70 bg-transparent px-4 py-2 text-xs text-red-300 hover:bg-red-900/30"
          data-test="swap-cancel"
          @click="cancel"
        >
          {{ t('swap.cancel') }}
        </button>
      </div>
    </div>
  </div>
</template>
