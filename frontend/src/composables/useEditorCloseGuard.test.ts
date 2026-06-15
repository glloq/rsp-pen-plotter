import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { useEditorCloseGuard, type EditorCloseGuardDeps } from './useEditorCloseGuard'

function setup(over: Partial<EditorCloseGuardDeps> = {}) {
  const onClose = vi.fn()
  const confirmDiscard = vi.fn().mockReturnValue(true)
  const deps: EditorCloseGuardDeps = {
    applying: ref(false),
    isDirty: ref(false),
    confirmDiscard,
    onClose,
    ...over,
  }
  return { deps, onClose, confirmDiscard, guard: useEditorCloseGuard(deps) }
}

describe('useEditorCloseGuard', () => {
  it('closes straight away when clean and not applying', () => {
    const { guard, onClose, confirmDiscard } = setup()
    guard.requestClose()
    expect(confirmDiscard).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('blocks the close while an expert apply is committing', () => {
    const { guard, onClose, confirmDiscard } = setup({ applying: ref(true), isDirty: ref(true) })
    guard.requestClose()
    expect(confirmDiscard).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('confirms before discarding an unsaved draft, then closes when accepted', () => {
    const confirmDiscard = vi.fn().mockReturnValue(true)
    const { guard, onClose } = setup({ isDirty: ref(true), confirmDiscard })
    guard.requestClose()
    expect(confirmDiscard).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('keeps the modal open when the discard is declined', () => {
    const confirmDiscard = vi.fn().mockReturnValue(false)
    const { guard, onClose } = setup({ isDirty: ref(true), confirmDiscard })
    guard.requestClose()
    expect(confirmDiscard).toHaveBeenCalledTimes(1)
    expect(onClose).not.toHaveBeenCalled()
  })
})
