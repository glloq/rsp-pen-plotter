// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import PromptDialog from './PromptDialog.vue'
import { promptText, resolvePrompt, usePromptState } from '../composables/prompt'

describe('PromptDialog', () => {
  beforeEach(() => {
    const state = usePromptState()
    // The composable is a module-level singleton; reset between tests
    // so a previous case can't leak an open dialog into the next.
    state.open = false
    state.resolve = null
  })

  afterEach(() => {
    const state = usePromptState()
    state.open = false
    state.resolve = null
  })

  it('renders nothing while the state is closed', () => {
    const wrapper = mount(PromptDialog)
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('renders title, message, labels and the initial value when opened', async () => {
    const wrapper = mount(PromptDialog)
    void promptText({
      title: 'New folder',
      message: '(sketches, maps)',
      initialValue: 'plots',
      confirmLabel: 'OK',
      cancelLabel: 'Cancel',
    })
    await nextTick()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('New folder')
    expect(wrapper.text()).toContain('(sketches, maps)')
    expect(wrapper.text()).toContain('OK')
    expect(wrapper.text()).toContain('Cancel')
    const input = wrapper.find('[data-test="prompt-input"]')
    expect((input.element as HTMLInputElement).value).toBe('plots')
  })

  it('submit resolves the promise with the typed value', async () => {
    const wrapper = mount(PromptDialog)
    const result = promptText({
      title: 't',
      confirmLabel: 'OK',
      cancelLabel: 'Cancel',
    })
    await nextTick()
    await wrapper.find('[data-test="prompt-input"]').setValue('birds')
    await wrapper.find('form').trigger('submit')
    await expect(result).resolves.toBe('birds')
  })

  it('cancel button resolves the promise with null', async () => {
    const wrapper = mount(PromptDialog)
    const result = promptText({
      title: 't',
      initialValue: 'kept-but-cancelled',
      confirmLabel: 'OK',
      cancelLabel: 'Cancel',
    })
    await nextTick()
    await wrapper.find('[data-test="prompt-cancel"]').trigger('click')
    await expect(result).resolves.toBeNull()
  })

  it('Escape in the input resolves with null', async () => {
    const wrapper = mount(PromptDialog)
    const result = promptText({
      title: 't',
      confirmLabel: 'OK',
      cancelLabel: 'Cancel',
    })
    await nextTick()
    await wrapper.find('[data-test="prompt-input"]').trigger('keydown', { key: 'Escape' })
    await expect(result).resolves.toBeNull()
  })

  it('clicking the backdrop resolves with null', async () => {
    // Same affordance as cancel — clicking outside the dialog is a
    // dismiss. The .self modifier guarantees the inner panel's click
    // doesn't bubble up and falsely trigger this path.
    const wrapper = mount(PromptDialog)
    const result = promptText({
      title: 't',
      confirmLabel: 'OK',
      cancelLabel: 'Cancel',
    })
    await nextTick()
    await wrapper.find('.fixed.inset-0').trigger('click')
    await expect(result).resolves.toBeNull()
    resolvePrompt(null)
  })

  it('a concurrent prompt settles the first one as cancelled', async () => {
    mount(PromptDialog)
    const first = promptText({ title: 'a', confirmLabel: 'OK', cancelLabel: 'Cancel' })
    const second = promptText({ title: 'b', confirmLabel: 'OK', cancelLabel: 'Cancel' })
    await nextTick()
    await expect(first).resolves.toBeNull()
    resolvePrompt('answer-b')
    await expect(second).resolves.toBe('answer-b')
  })
})
