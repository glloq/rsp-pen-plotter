import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ToastKind = 'info' | 'success' | 'warning' | 'error' | 'progress'

export interface ToastAction {
  /** Localised label shown on the action button. */
  label: string
  /** Invoked when the operator clicks the button. Implementations
   *  typically also dismiss the toast themselves. */
  onClick: () => void
}

export interface Toast {
  id: number
  kind: ToastKind
  message: string
  /** Optional time in ms before the toast auto-dismisses (default 6000, 0 = never). */
  ttl?: number
  /** Optional inline action button (e.g. "Cancel" for in-progress renders). */
  action?: ToastAction
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

  function show(
    kind: ToastKind,
    message: string,
    ttl: number = 6000,
    action?: ToastAction,
  ): number {
    const id = nextId++
    toasts.value = [...toasts.value, { id, kind, message, ttl, action }]
    if (ttl > 0) {
      timers.set(id, setTimeout(() => dismiss(id), ttl))
    }
    return id
  }

  const info = (message: string, ttl?: number) => show('info', message, ttl)
  const success = (message: string, ttl?: number) => show('success', message, ttl)
  const warning = (message: string, ttl?: number) => show('warning', message, ttl)
  const error = (message: string, ttl?: number) => show('error', message, ttl)

  // Persistent toast for in-progress operations. Returns an id; pass it to
  // ``update()`` or ``dismiss()`` when the operation completes. ttl=0 so it
  // stays visible (with spinner) until the caller resolves it. The optional
  // ``action`` wires up a cancel button (or similar) inline on the toast,
  // so the operator can interrupt a long-running render without hunting
  // for the right pane to click in.
  const progress = (message: string, action?: ToastAction): number =>
    show('progress', message, 0, action)

  // Transform an existing toast (typically a ``progress`` one) into a new
  // kind/message with a fresh ttl. Falls back to creating a new toast if
  // the id no longer exists (e.g. user dismissed it manually).
  function update(id: number, kind: ToastKind, message: string, ttl: number = 4000): number {
    const existing = toasts.value.find((t) => t.id === id)
    if (!existing) return show(kind, message, ttl)
    const timer = timers.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.delete(id)
    }
    toasts.value = toasts.value.map((t) =>
      t.id === id ? { ...t, kind, message, ttl } : t,
    )
    if (ttl > 0) {
      timers.set(id, setTimeout(() => dismiss(id), ttl))
    }
    return id
  }

  function clear(): void {
    for (const timer of timers.values()) clearTimeout(timer)
    timers.clear()
    toasts.value = []
  }

  return {
    toasts,
    show,
    dismiss,
    clear,
    info,
    success,
    warning,
    error,
    progress,
    update,
  }
})
