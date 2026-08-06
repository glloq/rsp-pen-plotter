<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { resolveConfirm, useConfirmState } from '../composables/confirm'

const state = useConfirmState()
const cancelEl = ref<HTMLButtonElement | null>(null)

// Move focus to the (safe) Cancel button when the dialog opens, so keyboard
// users land inside the overlay and Escape events originate here.
watch(
  () => state.open,
  async (open) => {
    if (!open) return
    await nextTick()
    cancelEl.value?.focus()
  },
)
</script>

<template>
  <div
    v-if="state.open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    @click.self="resolveConfirm(false)"
    @keydown.escape.stop.prevent="resolveConfirm(false)"
  >
    <div
      role="dialog"
      aria-modal="true"
      class="w-full max-w-sm rounded-lg border border-slate-700 bg-slate-800 p-5 shadow-xl"
    >
      <h2 class="text-base font-semibold text-slate-100">{{ state.title }}</h2>
      <p class="mt-2 text-sm text-slate-300">{{ state.message }}</p>
      <div class="mt-5 flex justify-end gap-2">
        <button
          ref="cancelEl"
          type="button"
          class="rounded bg-slate-700 px-4 py-2 text-sm text-slate-100 hover:bg-slate-600"
          data-test="confirm-dialog-cancel"
          @click="resolveConfirm(false)"
        >
          {{ state.cancelLabel }}
        </button>
        <button
          type="button"
          class="rounded px-4 py-2 text-sm font-medium text-white"
          :class="
            state.danger ? 'bg-red-700 hover:bg-red-600' : 'bg-emerald-600 hover:bg-emerald-500'
          "
          data-test="confirm-dialog-confirm"
          @click="resolveConfirm(true)"
        >
          {{ state.confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>
