// @vitest-environment happy-dom
/* eslint-disable vue/one-component-per-file --
   Throwaway host components per test case; not real SFCs. */
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { SHORTCUTS, _resetShortcutsForTests, useKeyboardShortcuts } from './useKeyboardShortcuts'

function press(
  key: string,
  opts: { meta?: boolean; ctrl?: boolean; target?: HTMLElement } = {},
): void {
  const event = new KeyboardEvent('keydown', {
    key,
    metaKey: opts.meta ?? false,
    ctrlKey: opts.ctrl ?? false,
    bubbles: true,
    cancelable: true,
  })
  if (opts.target) {
    Object.defineProperty(event, 'target', { value: opts.target })
    opts.target.dispatchEvent(event)
  } else {
    window.dispatchEvent(event)
  }
}

const Host = defineComponent({
  props: {
    onPause: { type: Function, required: true },
  },
  setup(props) {
    useKeyboardShortcuts([{ id: 'queue.pause', handler: () => (props.onPause as () => void)() }])
    return () => h('div')
  },
})

describe('useKeyboardShortcuts', () => {
  afterEach(() => {
    _resetShortcutsForTests()
  })

  it('exposes the canonical shortcut list for the help drawer', () => {
    expect(SHORTCUTS.length).toBeGreaterThan(0)
    for (const s of SHORTCUTS) {
      expect(s.id).toBeTruthy()
      expect(s.description).toBeTruthy()
    }
  })

  it('routes a registered Ctrl+K to its handler', () => {
    const onPause = vi.fn()
    mount(Host, { props: { onPause } })
    press('k', { ctrl: true })
    expect(onPause).toHaveBeenCalledOnce()
  })

  it('also accepts Cmd+K (macOS)', () => {
    const onPause = vi.fn()
    mount(Host, { props: { onPause } })
    press('k', { meta: true })
    expect(onPause).toHaveBeenCalledOnce()
  })

  it('ignores the same key without the modifier', () => {
    const onPause = vi.fn()
    mount(Host, { props: { onPause } })
    press('k')
    expect(onPause).not.toHaveBeenCalled()
  })

  it('does not intercept keys when the target is an input element', () => {
    const onPause = vi.fn()
    mount(Host, { props: { onPause } })
    const input = document.createElement('input')
    document.body.appendChild(input)
    press('k', { ctrl: true, target: input })
    expect(onPause).not.toHaveBeenCalled()
    document.body.removeChild(input)
  })

  it('triggers queue.resume on plain r without any modifier', () => {
    const onResume = vi.fn()
    const ResumeHost = defineComponent({
      setup() {
        useKeyboardShortcuts([{ id: 'queue.resume', handler: onResume }])
        return () => h('div')
      },
    })
    mount(ResumeHost)
    press('r')
    expect(onResume).toHaveBeenCalledOnce()
  })

  it('never intercepts Ctrl/Cmd+R (browser reload)', () => {
    const onResume = vi.fn()
    const ResumeHost = defineComponent({
      setup() {
        useKeyboardShortcuts([{ id: 'queue.resume', handler: onResume }])
        return () => h('div')
      },
    })
    mount(ResumeHost)
    const event = new KeyboardEvent('keydown', {
      key: 'r',
      ctrlKey: true,
      bubbles: true,
      cancelable: true,
    })
    window.dispatchEvent(event)
    expect(onResume).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })

  it('unregisters the handler on unmount', () => {
    const onPause = vi.fn()
    const wrapper = mount(Host, { props: { onPause } })
    wrapper.unmount()
    press('k', { ctrl: true })
    expect(onPause).not.toHaveBeenCalled()
  })
})
