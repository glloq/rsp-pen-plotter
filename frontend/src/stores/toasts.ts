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
  /** When true the toast stays until explicitly dismissed regardless of
   *  ttl. Reserved for critical events (operator-blocking errors,
   *  hardware loss) that must not vanish on a 6 s timer. */
  persistent?: boolean
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
    options: { persistent?: boolean } = {},
  ): number {
    const id = nextId++
    const persistent = options.persistent === true
    const effectiveTtl = persistent ? 0 : ttl
    toasts.value = [...toasts.value, { id, kind, message, ttl: effectiveTtl, action, persistent }]
    if (effectiveTtl > 0) {
      timers.set(
        id,
        setTimeout(() => dismiss(id), effectiveTtl),
      )
    }
    return id
  }

  const info = (message: string, ttl?: number) => show('info', message, ttl)
  const success = (message: string, ttl?: number) => show('success', message, ttl)
  const warning = (message: string, ttl?: number) => show('warning', message, ttl)
  const error = (message: string, ttl?: number) => show('error', message, ttl)
  /** Critical-severity error toast that never auto-dismisses — used
   *  for operator-blocking conditions (hardware loss, irrecoverable
   *  errors) that must not vanish on a 6 s timer. */
  const critical = (message: string, action?: ToastAction) =>
    show('error', message, 0, action, { persistent: true })

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
    toasts.value = toasts.value.map((t) => (t.id === id ? { ...t, kind, message, ttl } : t))
    if (ttl > 0) {
      timers.set(
        id,
        setTimeout(() => dismiss(id), ttl),
      )
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
    critical,
    progress,
    update,
  }
})
