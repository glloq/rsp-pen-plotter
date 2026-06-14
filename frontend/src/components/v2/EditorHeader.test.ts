// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createI18n } from 'vue-i18n'

import EditorHeader from './EditorHeader.vue'
import type { PreflightItem } from '../../composables/useEditorPreflight'

const i18n = createI18n({
  legacy: false,
  locale: 'fr',
  messages: {
    fr: {
      settings: { close: 'Fermer' },
      v2: {
        modal: {
          preflightLabel: 'Préparatifs',
          preflightFix: 'Corriger',
          estimateLabel: 'Durée estimée',
        },
      },
    },
  },
})

function items(over: Partial<PreflightItem>[] = []): PreflightItem[] {
  const base: PreflightItem[] = [
    { id: 'file', label: 'Fichier', ok: true, onFix: null },
    { id: 'machine', label: 'Machine', ok: true, onFix: null },
    { id: 'sheet', label: 'Feuille', ok: true, onFix: null },
    { id: 'inks', label: 'Encres', ok: true, onFix: null },
  ]
  return base.map((b, i) => ({ ...b, ...over[i] }))
}

function mountHeader(props: Record<string, unknown> = {}) {
  return mount(EditorHeader, {
    props: {
      hasPlacement: true,
      preflightItems: items(),
      hasEstimate: false,
      estimatedDurationSeconds: 0,
      estimatedLengthMm: 0,
      requiredPenCount: 0,
      isExpert: false,
      ...props,
    },
    global: { plugins: [i18n], stubs: { AssistantModeToggle: true } },
  })
}

describe('EditorHeader', () => {
  it('renders a chip per preflight item with its ready state', () => {
    const w = mountHeader()
    for (const id of ['file', 'machine', 'sheet', 'inks']) {
      expect(w.find(`[data-test="modal-v2-preflight-${id}"]`).exists()).toBe(true)
    }
  })

  it('renders an actionable button for a failing item with a fix and calls onFix', async () => {
    const onFix = vi.fn()
    const w = mountHeader({ preflightItems: items([{ ok: false, onFix }]) })
    const chip = w.find('[data-test="modal-v2-preflight-file"]')
    expect(chip.element.tagName).toBe('BUTTON')
    await chip.trigger('click')
    expect(onFix).toHaveBeenCalledTimes(1)
  })

  it('shows estimate chips only when hasEstimate, and a pen chip when pens are required', () => {
    const none = mountHeader({ hasEstimate: false, requiredPenCount: 0 })
    expect(none.find('[data-test="modal-v2-estimate-time"]').exists()).toBe(false)
    expect(none.find('[data-test="modal-v2-estimate-pens"]').exists()).toBe(false)

    const some = mountHeader({
      hasEstimate: true,
      estimatedDurationSeconds: 120,
      estimatedLengthMm: 2500,
      requiredPenCount: 3,
    })
    expect(some.find('[data-test="modal-v2-estimate-time"]').text()).toContain('2 min')
    expect(some.find('[data-test="modal-v2-estimate-length"]').text()).toContain('2.5')
    expect(some.find('[data-test="modal-v2-estimate-pens"]').text()).toContain('3')
  })

  it('hides the chip strip when there is no placement', () => {
    const w = mountHeader({ hasPlacement: false })
    expect(w.find('.modal-v2__header-chips').exists()).toBe(false)
  })

  it('emits close from the close button', async () => {
    const w = mountHeader()
    await w.find('[data-test="modal-v2-close"]').trigger('click')
    expect(w.emitted('close')).toBeTruthy()
  })
})
