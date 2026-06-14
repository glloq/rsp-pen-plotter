// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'

import EditorFooter from './EditorFooter.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'fr',
  messages: {
    fr: {
      v2: {
        modal: {
          cancel: 'Annuler',
          generate: 'Générer',
          noPlacement: 'Aucun placement actif',
          openExpert: 'Éditeur complet',
          openExpertHint: 'Ouvrir le mode expert',
          applyExpert: 'Appliquer',
          applyExpertHint: 'Reconvertir',
          applyExpertClean: 'Rien à appliquer',
          applyError: 'Échec : {message}.',
        },
      },
    },
  },
})

function mountFooter(props: Record<string, unknown> = {}) {
  return mount(EditorFooter, {
    props: {
      applyError: null,
      isAssisted: true,
      isExpert: false,
      isDirty: false,
      hasPlacement: true,
      applying: false,
      generateDisabled: false,
      ...props,
    },
    global: { plugins: [i18n] },
  })
}

describe('EditorFooter', () => {
  it('shows the expert link in assisted mode and not the apply button', () => {
    const w = mountFooter({ isAssisted: true, isExpert: false })
    expect(w.find('[data-test="modal-v2-open-expert"]').exists()).toBe(true)
    expect(w.find('[data-test="modal-v2-apply-expert"]').exists()).toBe(false)
  })

  it('shows the apply button in expert mode and not the expert link', () => {
    const w = mountFooter({ isAssisted: false, isExpert: true })
    expect(w.find('[data-test="modal-v2-apply-expert"]').exists()).toBe(true)
    expect(w.find('[data-test="modal-v2-open-expert"]').exists()).toBe(false)
  })

  it('disables Apply unless the draft is dirty, has a placement and is idle', () => {
    const clean = mountFooter({ isExpert: true, isDirty: false })
    expect(
      (clean.find('[data-test="modal-v2-apply-expert"]').element as HTMLButtonElement).disabled,
    ).toBe(true)
    const dirty = mountFooter({ isExpert: true, isDirty: true })
    expect(
      (dirty.find('[data-test="modal-v2-apply-expert"]').element as HTMLButtonElement).disabled,
    ).toBe(false)
    const busy = mountFooter({ isExpert: true, isDirty: true, applying: true })
    expect(
      (busy.find('[data-test="modal-v2-apply-expert"]').element as HTMLButtonElement).disabled,
    ).toBe(true)
  })

  it('reflects the generateDisabled prop on the Generate button', () => {
    const w = mountFooter({ generateDisabled: true })
    expect((w.find('[data-test="confirm-button"]').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('renders the apply error as an alert when present', () => {
    const w = mountFooter({ applyError: 'network down' })
    const err = w.find('[data-test="modal-v2-apply-error"]')
    expect(err.exists()).toBe(true)
    expect(err.attributes('role')).toBe('alert')
    expect(err.text()).toContain('network down')
  })

  it('emits the four actions on click', async () => {
    const w = mountFooter({ isExpert: true, isDirty: true, isAssisted: true })
    await w.find('[data-test="modal-v2-cancel"]').trigger('click')
    await w.find('[data-test="modal-v2-open-expert"]').trigger('click')
    await w.find('[data-test="modal-v2-apply-expert"]').trigger('click')
    await w.find('[data-test="confirm-button"]').trigger('click')
    expect(w.emitted('cancel')).toBeTruthy()
    expect(w.emitted('open-expert')).toBeTruthy()
    expect(w.emitted('apply')).toBeTruthy()
    expect(w.emitted('generate')).toBeTruthy()
  })
})
