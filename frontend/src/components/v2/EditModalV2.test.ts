// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createI18n } from 'vue-i18n'

vi.mock('../../api/client', () => ({ api: { post: vi.fn(), get: vi.fn() } }))

import { api } from '../../api/client'
import EditModalV2 from './EditModalV2.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'fr',
  fallbackLocale: 'fr',
  messages: {
    fr: {
      settings: { close: 'Fermer' },
      compare: { open: 'Comparer' },
      v2: {
        mode: { assisted: 'Assisté', expert: 'Expert' },
        modal: {
          title: "Préparer l'impression",
          generate: 'Générer',
          resolverError: 'Erreur resolver : {message}. Les défauts statiques seront utilisés.',
          openV1: "Ouvrir l'éditeur complet",
          layerCount: '{count} couche | {count} couches',
          noPlacement: 'Aucun placement actif',
          noPlacementTitle: 'Aucun placement actif',
          chooseIntent: 'Qu’est-ce qui compte le plus ?',
          previewLoading: 'Mise à jour de l’aperçu…',
          previewError: 'Aperçu indisponible.',
        },
        intent: {
          fast: 'Rapide',
          balanced: 'Équilibré',
          quality: 'Qualité',
          fastDesc: 'Tracé le plus rapide',
          balancedDesc: 'Bon défaut',
          qualityDesc: 'Détail maximal',
        },
      },
    },
  },
})

function mountModal(props?: Record<string, unknown>) {
  return mount(EditModalV2, { props, global: { plugins: [i18n] } })
}

const PLACEMENT_PROPS = {
  sourceName: 'photo.jpg',
  previewSvg: '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
}

const validDecision = {
  segmentation_method: 'fixed_palette',
  default_algorithm: 'scanlines',
  default_options: { spacing_px: 5, num_colors: 4 },
  quality_tier: 'draft',
  fallback_chain: ['halftone'],
  reasoning: [{ rule: 'bitmap_photo.fast', description: 'photo + fast' }],
  hard_constraints_applied: [],
}

describe('EditModalV2 (beginner single-screen)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
    vi.mocked(api.post).mockReset()
    vi.mocked(api.post).mockResolvedValue({ data: validDecision })
  })

  it('shows the live preview and the three intent cards when a placement is attached', () => {
    const wrapper = mountModal(PLACEMENT_PROPS)
    expect(wrapper.find('[data-test="modal-v2-preview"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="intent-fast"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="intent-balanced"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="intent-quality"]').exists()).toBe(true)
  })

  it('pre-selects the Balanced intent', () => {
    const wrapper = mountModal(PLACEMENT_PROPS)
    expect(wrapper.find('[data-test="intent-balanced"]').classes()).toContain('active')
  })

  it('auto-resolves the policy on mount with the balanced goal (zero clicks)', async () => {
    mountModal(PLACEMENT_PROPS)
    await flushPromises()
    expect(api.post).toHaveBeenCalledWith(
      '/policy/resolve',
      expect.objectContaining({ source_kind: 'bitmap_photo', goal: 'balanced' }),
    )
  })

  it('re-resolves when the operator picks a different intent', async () => {
    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()
    vi.mocked(api.post).mockClear()
    await wrapper.find('[data-test="intent-quality"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="intent-quality"]').classes()).toContain('active')
    expect(api.post).toHaveBeenCalledWith(
      '/policy/resolve',
      expect.objectContaining({ goal: 'quality' }),
    )
  })

  it('enables Generate once the decision resolves and emits confirm with it', async () => {
    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()
    const confirm = wrapper.find('[data-test="confirm-button"]')
    expect((confirm.element as HTMLButtonElement).disabled).toBe(false)
    await confirm.trigger('click')
    expect(wrapper.emitted('confirm')?.[0]?.[0]).toMatchObject({
      default_algorithm: 'scanlines',
    })
  })

  it('shows a no-placement notice + locks Generate when no source is attached', () => {
    const wrapper = mountModal()
    expect(wrapper.find('[data-test="modal-v2-no-placement"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="modal-v2-preview"]').exists()).toBe(false)
    const confirm = wrapper.find('[data-test="confirm-button"]')
    expect((confirm.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('surfaces resolver errors but keeps the original preview visible', async () => {
    vi.mocked(api.post).mockReset()
    vi.mocked(api.post).mockRejectedValue(new Error('500 oops'))
    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()
    expect(wrapper.find('[data-test="modal-v2-resolve-error"]').text()).toContain(
      'Erreur resolver',
    )
    expect(wrapper.find('[data-test="modal-v2-preview-svg"]').exists()).toBe(true)
  })

  it('emits cancel on the close button', async () => {
    const wrapper = mountModal(PLACEMENT_PROPS)
    await wrapper.find('button[aria-label="Fermer"]').trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
  })

  it('emits open-v1 when the operator opens the full editor', async () => {
    const wrapper = mountModal(PLACEMENT_PROPS)
    await wrapper.find('[data-test="modal-v2-open-v1"]').trigger('click')
    expect(wrapper.emitted('open-v1')).toBeTruthy()
  })

  it('backdrop click emits cancel', async () => {
    const wrapper = mountModal(PLACEMENT_PROPS)
    await wrapper.find('[data-test="modal-v2-backdrop"]').trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
  })

  it('Escape key emits cancel (accessibility)', async () => {
    const wrapper = mountModal({ ...PLACEMENT_PROPS, attachTo: document.body })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(wrapper.emitted('cancel')).toBeTruthy()
    wrapper.unmount()
  })
})
