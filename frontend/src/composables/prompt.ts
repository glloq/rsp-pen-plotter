import { reactive } from 'vue'

export interface PromptOptions {
  title: string
  message?: string
  placeholder?: string
  initialValue?: string
  confirmLabel: string
  cancelLabel: string
}

interface PromptState {
  open: boolean
  title: string
  message: string
  placeholder: string
  value: string
  confirmLabel: string
  cancelLabel: string
  resolve: ((value: string | null) => void) | null
}

const state = reactive<PromptState>({
  open: false,
  title: '',
  message: '',
  placeholder: '',
  value: '',
  confirmLabel: '',
  cancelLabel: '',
  resolve: null,
})

export function usePromptState(): PromptState {
  return state
}

// Text-input twin of ``confirmAction`` — resolves with the typed string on
// confirm and ``null`` on dismiss (cancel button, backdrop click or Escape).
// Replaces the native ``window.prompt``, which blocks the event loop and is
// unusable on tablets / kiosk browsers.
export function promptText(options: PromptOptions): Promise<string | null> {
  // A second concurrent promptText() would otherwise silently overwrite
  // ``state.resolve`` and leave the first awaiter hanging forever. Settle
  // the previous prompt as "cancelled" before the new one takes over the
  // singleton dialog state (same rule as confirmAction).
  state.resolve?.(null)
  state.resolve = null
  state.title = options.title
  state.message = options.message ?? ''
  state.placeholder = options.placeholder ?? ''
  state.value = options.initialValue ?? ''
  state.confirmLabel = options.confirmLabel
  state.cancelLabel = options.cancelLabel
  state.open = true
  return new Promise((resolve) => {
    state.resolve = resolve
  })
}

export function resolvePrompt(value: string | null): void {
  state.open = false
  state.resolve?.(value)
  state.resolve = null
}
