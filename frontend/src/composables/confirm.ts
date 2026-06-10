import { reactive } from 'vue'

export interface ConfirmOptions {
  title: string
  message: string
  confirmLabel: string
  cancelLabel: string
  danger?: boolean
}

interface ConfirmState extends ConfirmOptions {
  open: boolean
  resolve: ((value: boolean) => void) | null
}

const state = reactive<ConfirmState>({
  open: false,
  title: '',
  message: '',
  confirmLabel: '',
  cancelLabel: '',
  danger: false,
  resolve: null,
})

export function useConfirmState(): ConfirmState {
  return state
}

export function confirmAction(options: ConfirmOptions): Promise<boolean> {
  // A second concurrent confirmAction() would otherwise silently
  // overwrite ``state.resolve`` and leave the first awaiter hanging
  // forever. Settle the previous prompt as "cancelled" before the new
  // one takes over the singleton dialog state.
  state.resolve?.(false)
  state.resolve = null
  state.title = options.title
  state.message = options.message
  state.confirmLabel = options.confirmLabel
  state.cancelLabel = options.cancelLabel
  state.danger = options.danger ?? false
  state.open = true
  return new Promise((resolve) => {
    state.resolve = resolve
  })
}

export function resolveConfirm(value: boolean): void {
  state.open = false
  state.resolve?.(value)
  state.resolve = null
}
