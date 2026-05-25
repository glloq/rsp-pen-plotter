// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import Toasts from './Toasts.vue'
import { useToastStore } from '../stores/toasts'

describe('Toasts', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    // Each test starts with no active timers — the toast store
    // schedules auto-dismiss via setTimeout and we don't want one
    // case's pending timer to interfere with the next.
    vi.useFakeTimers()
  })

  it('renders nothing when the queue is empty', () => {
    // The aria-live region still mounts (assistive tech expects it to
    // be present continuously), but no toast children should appear.
    const wrapper = mount(Toasts)
    expect(wrapper.find('[role="region"]').exists()).toBe(true)
    expect(wrapper.findAll('[role="status"]')).toHaveLength(0)
  })

  it('renders a toast for each entry in the store', async () => {
    const store = useToastStore()
    store.show('info', 'Connected')
    store.show('success', 'Saved')
    store.show('error', 'Boom')
    const wrapper = mount(Toasts)
    await nextTick()
    expect(wrapper.findAll('[role="status"]')).toHaveLength(3)
    expect(wrapper.text()).toContain('Connected')
    expect(wrapper.text()).toContain('Saved')
    expect(wrapper.text()).toContain('Boom')
  })

  it('applies the right tone classes per kind', async () => {
    const store = useToastStore()
    store.show('error', 'fail', 0)
    store.show('success', 'ok', 0)
    const wrapper = mount(Toasts)
    await nextTick()
    const items = wrapper.findAll('[role="status"]')
    const klasses = items.map((i) => i.classes().join(' '))
    expect(klasses.some((c) => c.includes('text-red-100'))).toBe(true)
    expect(klasses.some((c) => c.includes('text-emerald-100'))).toBe(true)
  })

  it('the dismiss button removes the toast from the queue', async () => {
    const store = useToastStore()
    store.show('info', 'Hello', 0)
    const wrapper = mount(Toasts)
    await nextTick()
    expect(store.toasts).toHaveLength(1)
    const dismiss = wrapper.find('button[aria-label="Dismiss"]')
    await dismiss.trigger('click')
    expect(store.toasts).toHaveLength(0)
  })

  it('progress toasts show a spinner and no dismiss button', async () => {
    // Progress toasts are owned by the long-running operation that
    // started them; the operator dismisses them by cancelling, not by
    // clicking the corner ✕. The ✕ should therefore not render at all.
    const store = useToastStore()
    store.show('progress', 'Generating G-code…', 0)
    const wrapper = mount(Toasts)
    await nextTick()
    expect(wrapper.find('[role="status"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="Dismiss"]').exists()).toBe(false)
    expect(wrapper.find('.animate-spin').exists()).toBe(true)
  })

  it('renders the inline action button when ``action`` is set', async () => {
    const clicked = vi.fn()
    const store = useToastStore()
    store.show('info', 'Updates available', 0, {
      label: 'Open settings',
      onClick: clicked,
    })
    const wrapper = mount(Toasts)
    await nextTick()
    const action = wrapper.findAll('button').find((b) => b.text() === 'Open settings')
    expect(action).toBeTruthy()
    await action!.trigger('click')
    expect(clicked).toHaveBeenCalledOnce()
  })
})
