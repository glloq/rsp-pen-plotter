// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'

import EditorHeader from './EditorHeader.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'fr',
  messages: {
    fr: {
      settings: { close: 'Fermer' },
      v2: {
        modal: {
          saveStyle: 'Enregistrer le style',
          saveStyleHint: 'Enregistre le style',
          noPlacement: 'Aucun placement actif',
        },
      },
    },
  },
})

function mountHeader(props: Record<string, unknown> = {}) {
  return mount(EditorHeader, {
    props: {
      hasPlacement: true,
      saveDisabled: false,
      ...props,
    },
    // Stub the stateful children — they own their own store wiring and
    // are covered by their own specs. This header test only cares about
    // the three-zone composition + the save / close affordances.
    global: { plugins: [i18n], stubs: { AssistantModeToggle: true, SheetPicker: true } },
  })
}

describe('EditorHeader', () => {
  it('renders the mode toggle in the centre zone', () => {
    const w = mountHeader()
    expect(w.find('.modal-v2__header-center assistant-mode-toggle-stub').exists()).toBe(true)
  })

  it('renders the sheet picker (above the preview) when there is a placement', () => {
    const w = mountHeader({ hasPlacement: true })
    expect(w.find('.modal-v2__header-left sheet-picker-stub').exists()).toBe(true)
  })

  it('hides the sheet picker when there is no placement', () => {
    const w = mountHeader({ hasPlacement: false })
    expect(w.find('sheet-picker-stub').exists()).toBe(false)
  })

  it('exposes a single save button in the right zone and emits save on click', async () => {
    const w = mountHeader()
    const save = w.find('[data-test="confirm-button"]')
    expect(save.exists()).toBe(true)
    expect(save.text()).toContain('Enregistrer le style')
    await save.trigger('click')
    expect(w.emitted('save')).toBeTruthy()
  })

  it('disables the save button when saveDisabled is set', () => {
    const w = mountHeader({ saveDisabled: true })
    expect((w.find('[data-test="confirm-button"]').element as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it('emits close from the close button', async () => {
    const w = mountHeader()
    await w.find('[data-test="modal-v2-close"]').trigger('click')
    expect(w.emitted('close')).toBeTruthy()
  })

  it('does not render the old preflight / estimate status chips', () => {
    const w = mountHeader()
    expect(w.find('.modal-v2__header-chips').exists()).toBe(false)
    expect(w.find('[data-test="modal-v2-estimate-time"]').exists()).toBe(false)
  })
})
