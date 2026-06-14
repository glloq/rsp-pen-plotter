// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'

import EditorAssistedPanel from './EditorAssistedPanel.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'fr',
  messages: {
    fr: {
      v2: {
        modal: {
          chooseIntent: 'Priorité ?',
          paletteLabel: 'Couleurs',
          paletteMachine: 'Magazine',
          paletteFree: 'Libre',
        },
        intent: {
          fast: 'Rapide',
          balanced: 'Équilibré',
          quality: 'Qualité',
          fastDesc: 'a',
          balancedDesc: 'b',
          qualityDesc: 'c',
        },
      },
    },
  },
})

const StyleCustomizerStub = {
  name: 'StyleCustomizer',
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template: '<div data-test="stub-style" @click="$emit(\'update:modelValue\', [{ id: \'x\' }])" />',
}

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(EditorAssistedPanel, {
    props: {
      goal: 'balanced',
      paletteMode: 'machine_only',
      canCustomizeStyles: true,
      customStyles: [],
      ...props,
    },
    global: { plugins: [i18n], stubs: { StyleCustomizer: StyleCustomizerStub } },
  })
}

describe('EditorAssistedPanel', () => {
  it('marks the active intent and palette from props', () => {
    const w = mountPanel({ goal: 'quality', paletteMode: 'free' })
    expect(w.find('[data-test="intent-quality"]').classes()).toContain('active')
    expect(w.find('[data-test="intent-fast"]').classes()).not.toContain('active')
    expect(w.find('[data-test="palette-free"]').classes()).toContain('active')
    expect(w.find('[data-test="palette-machine_only"]').classes()).not.toContain('active')
  })

  it('emits select-goal and select-palette on click', async () => {
    const w = mountPanel()
    await w.find('[data-test="intent-fast"]').trigger('click')
    await w.find('[data-test="palette-free"]').trigger('click')
    expect(w.emitted('select-goal')).toEqual([['fast']])
    expect(w.emitted('select-palette')).toEqual([['free']])
  })

  it('shows the style customizer only for bitmap sources', () => {
    expect(mountPanel({ canCustomizeStyles: true }).find('[data-test="stub-style"]').exists()).toBe(
      true,
    )
    expect(
      mountPanel({ canCustomizeStyles: false }).find('[data-test="stub-style"]').exists(),
    ).toBe(false)
  })

  it('forwards the style customizer update as update:customStyles', async () => {
    const w = mountPanel()
    await w.find('[data-test="stub-style"]').trigger('click')
    expect(w.emitted('update:customStyles')).toEqual([[[{ id: 'x' }]]])
  })
})
