<script setup lang="ts">
import { useToastStore, type ToastKind } from '../stores/toasts'

const store = useToastStore()

const toneClass: Record<ToastKind, string> = {
  info: 'border-sky-700 bg-sky-950/80 text-sky-100',
  success: 'border-emerald-700 bg-emerald-950/80 text-emerald-100',
  warning: 'border-amber-700 bg-amber-950/80 text-amber-100',
  error: 'border-red-700 bg-red-950/80 text-red-100',
  progress: 'border-slate-600 bg-slate-900/80 text-slate-100',
}

const icon: Record<ToastKind, string> = {
  info: 'ℹ',
  success: '✓',
  warning: '⚠',
  error: '✕',
  progress: '',
}
</script>

<template>
  <div
    class="pointer-events-none fixed bottom-3 right-3 z-50 flex w-full max-w-sm flex-col gap-2"
    role="region"
    aria-live="polite"
  >
    <transition-group name="toast">
      <div
        v-for="toast in store.toasts"
        :key="toast.id"
        class="pointer-events-auto flex items-start gap-2 rounded-lg border px-3 py-2 text-sm shadow-lg backdrop-blur"
        :class="toneClass[toast.kind]"
        role="status"
      >
        <span
          v-if="toast.kind === 'progress'"
          class="mt-0.5 inline-block h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-slate-500 border-t-slate-200"
          aria-hidden="true"
        />
        <span v-else class="mt-0.5 shrink-0 font-bold leading-none">{{ icon[toast.kind] }}</span>
        <p class="min-w-0 flex-1 whitespace-pre-wrap break-words">{{ toast.message }}</p>
        <button
          v-if="toast.kind !== 'progress'"
          type="button"
          class="shrink-0 rounded p-1 leading-none text-slate-300 hover:bg-white/10 hover:text-white"
          aria-label="Dismiss"
          @click="store.dismiss(toast.id)"
        >
          ×
        </button>
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 200ms ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(20px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
.toast-leave-active {
  position: absolute;
  right: 0;
  width: 100%;
}
</style>
