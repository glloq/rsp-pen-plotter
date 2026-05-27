// Keyboard shortcuts composable (roadmap C.9).
//
// One global keydown listener routes Ctrl/Cmd + letter combos to
// registered handlers. The mapping is exposed as `SHORTCUTS` so the
// Help drawer (or `docs/shortcuts.md`) can render it without
// duplicating the source of truth.
//
// Designed to be additive: a component calls `register(id, fn)` on
// mount and the matching binding becomes active; `unregister(id)` on
// unmount removes it. Keyboard input that targets an editable surface
// (input / textarea / contenteditable) is **not** intercepted, so the
// shortcuts never eat normal typing.

import { onBeforeUnmount, onMounted } from 'vue'

export interface ShortcutBinding {
  id: string
  /** Lowercase key (e.g. 'k', 'enter'). */
  key: string
  /** Required modifier — Ctrl on Win/Linux, Cmd on macOS. */
  mod: 'ctrl_or_meta' | 'shift' | 'none'
  description: string
}

export const SHORTCUTS: readonly ShortcutBinding[] = [
  { id: 'modal.next', key: 'enter', mod: 'ctrl_or_meta', description: 'Next step in the modal' },
  { id: 'modal.previous', key: 'backspace', mod: 'ctrl_or_meta', description: 'Previous step in the modal' },
  { id: 'mode.toggle', key: 'm', mod: 'ctrl_or_meta', description: 'Toggle assisted / expert mode' },
  { id: 'perf.toggle', key: 'p', mod: 'ctrl_or_meta', description: 'Toggle perf overlay' },
  { id: 'queue.pause', key: 'k', mod: 'ctrl_or_meta', description: 'Pause active run' },
  { id: 'queue.resume', key: 'r', mod: 'ctrl_or_meta', description: 'Resume active run' },
]

const handlers = new Map<string, () => void>()

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

function matches(binding: ShortcutBinding, event: KeyboardEvent): boolean {
  if (event.key.toLowerCase() !== binding.key) return false
  if (binding.mod === 'ctrl_or_meta') return event.ctrlKey || event.metaKey
  if (binding.mod === 'shift') return event.shiftKey
  return !event.ctrlKey && !event.metaKey && !event.shiftKey
}

let installed = false

function installListener(): void {
  if (installed) return
  installed = true
  window.addEventListener('keydown', (event) => {
    if (isEditable(event.target)) return
    for (const binding of SHORTCUTS) {
      if (matches(binding, event)) {
        const handler = handlers.get(binding.id)
        if (handler) {
          event.preventDefault()
          handler()
        }
        return
      }
    }
  })
}

export function useKeyboardShortcuts(
  registrations: { id: string; handler: () => void }[],
): void {
  onMounted(() => {
    installListener()
    for (const r of registrations) handlers.set(r.id, r.handler)
  })
  onBeforeUnmount(() => {
    for (const r of registrations) handlers.delete(r.id)
  })
}

/** Test-only — clear the global state. */
export function _resetShortcutsForTests(): void {
  handlers.clear()
}
