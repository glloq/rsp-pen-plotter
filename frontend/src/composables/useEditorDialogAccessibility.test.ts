// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { useEditorDialogAccessibility } from './useEditorDialogAccessibility'

let opener: HTMLButtonElement
let dialog: HTMLDivElement
let btnFirst: HTMLButtonElement
let btnMid: HTMLButtonElement
let btnLast: HTMLButtonElement

function build() {
  document.body.innerHTML = ''
  opener = document.createElement('button')
  opener.textContent = 'open'
  document.body.appendChild(opener)

  dialog = document.createElement('div')
  btnFirst = document.createElement('button')
  btnMid = document.createElement('button')
  btnLast = document.createElement('button')
  btnFirst.textContent = 'first'
  btnMid.textContent = 'mid'
  btnLast.textContent = 'last'
  dialog.append(btnFirst, btnMid, btnLast)
  document.body.appendChild(dialog)
}

function tab(shift = false) {
  window.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'Tab', shiftKey: shift, bubbles: true, cancelable: true }),
  )
}

describe('useEditorDialogAccessibility', () => {
  beforeEach(() => build())
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('calls onEscape when Escape is pressed', () => {
    const onEscape = vi.fn()
    const a11y = useEditorDialogAccessibility({ dialogRoot: ref(dialog), onEscape })
    a11y.activate()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', cancelable: true }))
    expect(onEscape).toHaveBeenCalledTimes(1)
    a11y.deactivate()
  })

  it('moves focus to the first control on focusInitial', () => {
    const a11y = useEditorDialogAccessibility({ dialogRoot: ref(dialog), onEscape: () => {} })
    a11y.activate()
    a11y.focusInitial()
    expect(document.activeElement).toBe(btnFirst)
    a11y.deactivate()
  })

  it('wraps Tab from the last control back to the first', () => {
    const a11y = useEditorDialogAccessibility({ dialogRoot: ref(dialog), onEscape: () => {} })
    a11y.activate()
    btnLast.focus()
    tab()
    expect(document.activeElement).toBe(btnFirst)
    a11y.deactivate()
  })

  it('wraps Shift+Tab from the first control back to the last', () => {
    const a11y = useEditorDialogAccessibility({ dialogRoot: ref(dialog), onEscape: () => {} })
    a11y.activate()
    btnFirst.focus()
    tab(true)
    expect(document.activeElement).toBe(btnLast)
    a11y.deactivate()
  })

  it('pulls focus back into the dialog when Tab fires from outside the ring', () => {
    const a11y = useEditorDialogAccessibility({ dialogRoot: ref(dialog), onEscape: () => {} })
    a11y.activate()
    opener.focus() // focus outside the dialog
    tab()
    expect(document.activeElement).toBe(btnFirst)
    a11y.deactivate()
  })

  it('restores focus to the opener on deactivate', () => {
    opener.focus()
    const a11y = useEditorDialogAccessibility({ dialogRoot: ref(dialog), onEscape: () => {} })
    a11y.activate() // captures ``opener`` as the active element
    a11y.focusInitial() // focus moves into the dialog
    expect(document.activeElement).toBe(btnFirst)
    a11y.deactivate()
    expect(document.activeElement).toBe(opener)
  })

  it('does not throw when the opener has been detached', () => {
    opener.focus()
    const a11y = useEditorDialogAccessibility({ dialogRoot: ref(dialog), onEscape: () => {} })
    a11y.activate()
    opener.remove() // opener gone before close
    expect(() => a11y.deactivate()).not.toThrow()
  })

  it('skips aria-disabled and hidden controls in the tab ring', () => {
    btnFirst.setAttribute('aria-disabled', 'true')
    btnMid.hidden = true
    const a11y = useEditorDialogAccessibility({ dialogRoot: ref(dialog), onEscape: () => {} })
    a11y.activate()
    // Only btnLast remains tabbable → focusInitial lands on it, and a
    // forward Tab from it wraps back to it.
    a11y.focusInitial()
    expect(document.activeElement).toBe(btnLast)
    a11y.deactivate()
  })

  it('follows content that mounts after activation', () => {
    const a11y = useEditorDialogAccessibility({ dialogRoot: ref(dialog), onEscape: () => {} })
    a11y.activate()
    // A lazily-mounted control appended after open joins the ring.
    const late = document.createElement('button')
    late.textContent = 'late'
    dialog.appendChild(late)
    late.focus()
    tab() // ``late`` is now the last element → wraps to first
    expect(document.activeElement).toBe(btnFirst)
    a11y.deactivate()
  })

  it('stops trapping after deactivate', () => {
    const onEscape = vi.fn()
    const a11y = useEditorDialogAccessibility({ dialogRoot: ref(dialog), onEscape })
    a11y.activate()
    a11y.deactivate()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', cancelable: true }))
    expect(onEscape).not.toHaveBeenCalled()
  })
})
