<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { resolvePrompt, usePromptState } from '../composables/prompt'

const state = usePromptState()
const inputEl = ref<HTMLInputElement | null>(null)

watch(
  () => state.open,
  async (open) => {
    if (!open) return
    await nextTick()
    inputEl.value?.focus()
    inputEl.value?.select()
  },
)
</script>

<template>
  <div
    v-if="state.open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    @click.self="resolvePrompt(null)"
  >
    <form
      role="dialog"
      aria-modal="true"
      class="w-full max-w-sm rounded-lg border border-slate-700 bg-slate-800 p-5 shadow-xl"
      @submit.prevent="resolvePrompt(state.value)"
    >
      <h2 class="text-base font-semibold text-slate-100">{{ state.title }}</h2>
      <p v-if="state.message" class="mt-2 text-sm text-slate-300">{{ state.message }}</p>
      <input
        ref="inputEl"
        v-model="state.value"
        type="text"
        :placeholder="state.placeholder"
        class="mt-3 w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus:border-sky-500 focus:outline-none"
        data-test="prompt-input"
        @keydown.escape.prevent="resolvePrompt(null)"
      />
      <div class="mt-5 flex justify-end gap-2">
        <button
          type="button"
          class="rounded bg-slate-700 px-4 py-2 text-sm text-slate-100 hover:bg-slate-600"
          data-test="prompt-cancel"
          @click="resolvePrompt(null)"
        >
          {{ state.cancelLabel }}
        </button>
        <button
          type="submit"
          class="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500"
          data-test="prompt-confirm"
        >
          {{ state.confirmLabel }}
        </button>
      </div>
    </form>
  </div>
</template>
