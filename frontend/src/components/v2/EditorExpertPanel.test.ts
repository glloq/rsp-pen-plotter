// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import EditorExpertPanel from './EditorExpertPanel.vue'

const tabStubs = {
  EditTabs: {
    name: 'EditTabs',
    props: ['modelValue', 'layerCount', 'showText'],
    emits: ['update:modelValue'],
    template:
      '<div role="tablist" data-test="stub-tabs" @click="$emit(\'update:modelValue\', \'svg\')" />',
  },
  ImageTab: { template: '<div data-test="stub-image" />' },
  SvgTab: { template: '<div data-test="stub-svg" />' },
  StyleTab: { template: '<div data-test="stub-style" />' },
  TextTab: { template: '<div data-test="stub-text" />' },
  LayersSection: { template: '<div data-test="stub-layers" />' },
}

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(EditorExpertPanel, {
    props: { activeTab: 'image', layerCount: 3, showText: false, ...props },
    global: { stubs: tabStubs },
  })
}

describe('EditorExpertPanel', () => {
  it('renders the expert panel section and the tab strip', () => {
    const w = mountPanel()
    expect(w.find('[data-test="modal-v2-expert-panel"]').exists()).toBe(true)
    expect(w.find('[data-test="stub-tabs"]').exists()).toBe(true)
  })

  it('forwards layer-count / show-text / active tab to EditTabs', () => {
    const w = mountPanel({ layerCount: 5, showText: true, activeTab: 'text' })
    const tabs = w.findComponent({ name: 'EditTabs' })
    expect(tabs.props('layerCount')).toBe(5)
    expect(tabs.props('showText')).toBe(true)
    expect(tabs.props('modelValue')).toBe('text')
  })

  it('re-emits the tab strip selection as update:active-tab', async () => {
    const w = mountPanel()
    await w.find('[data-test="stub-tabs"]').trigger('click') // stub emits 'svg'
    expect(w.emitted('update:active-tab')).toEqual([['svg']])
  })

  it('shows only the content for the active tab', async () => {
    const w = mountPanel({ activeTab: 'layers' })
    await flushPromises()
    expect(w.find('[data-test="stub-layers"]').exists()).toBe(true)
    expect(w.find('[data-test="stub-image"]').exists()).toBe(false)

    await w.setProps({ activeTab: 'style' })
    await flushPromises()
    expect(w.find('[data-test="stub-style"]').exists()).toBe(true)
    expect(w.find('[data-test="stub-layers"]').exists()).toBe(false)
  })
})
