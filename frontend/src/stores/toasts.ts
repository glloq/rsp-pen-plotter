import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ToastKind = 'info' | 'success' | 'warning' | 'error'

export interface Toast {
  id: number
  kind: ToastKind
  message: string
  /** Optional time in ms before the toast auto-dismisses (default 6000). */
  ttl?: number
}

let nextId = 1

export const useToastStore = defineStore('toasts', () => {
  const toasts = ref<Toast[]>([])
  const timers = new Map<number, ReturnType<typeof setTimeout>>()

  function dismiss(id: number): void {
    const timer = timers.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.delete(id)
    }
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }

  function show(kind: ToastKind, message: string, ttl: number = 6000): number {
    const id = nextId++
    toasts.value = [...toasts.value, { id, kind, message, ttl }]
    if (ttl > 0) {
      timers.set(id, setTimeout(() => dismiss(id), ttl))
    }
    return id
  }

  const info = (message: string, ttl?: number) => show('info', message, ttl)
  const success = (message: string, ttl?: number) => show('success', message, ttl)
  const warning = (message: string, ttl?: number) => show('warning', message, ttl)
  const error = (message: string, ttl?: number) => show('error', message, ttl)

  function clear(): void {
    for (const timer of timers.values()) clearTimeout(timer)
    timers.clear()
    toasts.value = []
  }

  return { toasts, show, dismiss, clear, info, success, warning, error }
})
