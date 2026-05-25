// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import ConfirmDialog from './ConfirmDialog.vue'
import { confirmAction, resolveConfirm, useConfirmState } from '../composables/confirm'

describe('ConfirmDialog', () => {
  beforeEach(() => {
    const state = useConfirmState()
    // The composable is a module-level singleton; reset between tests
    // so a previous case can't leak an open dialog into the next.
    state.open = false
    state.resolve = null
  })

  afterEach(() => {
    const state = useConfirmState()
    state.open = false
    state.resolve = null
  })

  it('renders nothing while the state is closed', () => {
    // Default state has open=false; the v-if must hide the whole
    // overlay so it doesn't intercept clicks behind it.
    const wrapper = mount(ConfirmDialog)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('renders title, message and labels when opened', async () => {
    const wrapper = mount(ConfirmDialog)
    void confirmAction({
      title: 'Stop generation?',
      message: 'You have unsaved changes.',
      confirmLabel: 'Stop',
      cancelLabel: 'Keep going',
      danger: true,
    })
    await nextTick()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Stop generation?')
    expect(wrapper.text()).toContain('You have unsaved changes.')
    expect(wrapper.text()).toContain('Stop')
    expect(wrapper.text()).toContain('Keep going')
    // Danger styling on the confirm button.
    const confirmBtn = wrapper.findAll('button').find((b) => b.text() === 'Stop')
    expect(confirmBtn?.classes().join(' ')).toContain('bg-red-700')
  })

  it('confirm button resolves the promise with true', async () => {
    const wrapper = mount(ConfirmDialog)
    const result = confirmAction({
      title: 't',
      message: 'm',
      confirmLabel: 'OK',
      cancelLabel: 'Cancel',
    })
    await nextTick()
    const ok = wrapper.findAll('button').find((b) => b.text() === 'OK')
    await ok!.trigger('click')
    await expect(result).resolves.toBe(true)
  })

  it('cancel button resolves the promise with false', async () => {
    const wrapper = mount(ConfirmDialog)
    const result = confirmAction({
      title: 't',
      message: 'm',
      confirmLabel: 'OK',
      cancelLabel: 'Cancel',
    })
    await nextTick()
    const cancel = wrapper.findAll('button').find((b) => b.text() === 'Cancel')
    await cancel!.trigger('click')
    await expect(result).resolves.toBe(false)
  })

  it('clicking the backdrop resolves with false', async () => {
    // Same affordance as cancel — clicking outside the dialog is a
    // dismiss. The .self modifier guarantees the inner panel's click
    // doesn't bubble up and falsely trigger this path.
    const wrapper = mount(ConfirmDialog)
    const result = confirmAction({
      title: 't',
      message: 'm',
      confirmLabel: 'OK',
      cancelLabel: 'Cancel',
    })
    await nextTick()
    // The overlay is the first div with .fixed.inset-0
    const overlay = wrapper.find('.fixed.inset-0')
    await overlay.trigger('click')
    // The .self modifier means we need to dispatch with the overlay as
    // target — Vue Test Utils does this naturally when triggering on
    // the element itself.
    await expect(result).resolves.toBe(false)
    // Direct API matches the click path too.
    resolveConfirm(false)
  })
})
