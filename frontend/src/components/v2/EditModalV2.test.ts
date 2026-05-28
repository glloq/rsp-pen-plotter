// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
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
      v2: {
        mode: { assisted: 'Assisté', expert: 'Expert' },
        modal: {
          title: "Préparer l'impression",
          stepSource: 'Source',
          stepIntent: 'Intent',
          stepAlgorithm: 'Algorithme',
          stepColors: 'Couleurs',
          stepLayers: 'Couches',
          stepPreflight: 'Préflight',
          previous: 'Précédent',
          next: 'Suivant',
          generate: 'Générer',
          why: 'Pourquoi ce choix ?',
          resolving: 'Calcul…',
          resolverError: 'Erreur resolver : {message}. Les défauts statiques seront utilisés.',
          openV1: 'Ouvrir l\'éditeur complet',
          layerCount: '{count} couche | {count} couches',
          noPlacement: 'Aucun placement actif',
        },
        intent: { fast: 'Rapide', balanced: 'Équilibré', quality: 'Qualité' },
      },
    },
  },
})

function mountModal(props?: Record<string, unknown>) {
  return mount(EditModalV2, { props, global: { plugins: [i18n] } })
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

describe('EditModalV2', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
    vi.mocked(api.post).mockReset()
  })

  it('renders the stepper with six steps and starts on Source', () => {
    const wrapper = mountModal()
    const steps = wrapper.findAll('[data-test^="stepper-step-"]')
    expect(steps).toHaveLength(6)
    expect(wrapper.find('[data-test="step-source"]').exists()).toBe(true)
  })

  it('walks forward Source -> Intent and lets the operator pick a goal', async () => {
    const wrapper = mountModal()
    await wrapper.find('button:nth-child(2)').trigger('click') // ignore; use Suivant
    // Click "Suivant" instead.
    const nextButton = wrapper
      .findAll('button')
      .find((b) => b.text() === 'Suivant')
    await nextButton!.trigger('click')
    expect(wrapper.find('[data-test="step-intent"]').exists()).toBe(true)
    await wrapper.find('[data-test="intent-quality"]').trigger('click')
    expect(
      wrapper.find('[data-test="intent-quality"]').classes(),
    ).toContain('active')
  })

  it('calls /policy/resolve when leaving Intent and renders the recommendation', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: validDecision })
    const wrapper = mountModal()
    // Source -> Intent.
    let next = () =>
      wrapper.findAll('button').find((b) => b.text() === 'Suivant')!
    await next().trigger('click')
    // Intent -> Algorithm; triggers the resolver call.
    await next().trigger('click')
    await nextTick()
    await nextTick()
    expect(api.post).toHaveBeenCalledWith(
      '/policy/resolve',
      expect.objectContaining({ source_kind: 'bitmap_photo', goal: 'fast' }),
    )
    expect(wrapper.find('[data-test="recommended-algo"]').text()).toBe('scanlines')
  })

  it('shows reasoning entries from the decision', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: validDecision })
    const wrapper = mountModal()
    const next = () =>
      wrapper.findAll('button').find((b) => b.text() === 'Suivant')!
    await next().trigger('click')
    await next().trigger('click')
    await nextTick()
    await nextTick()
    expect(wrapper.text()).toContain('photo + fast')
  })

  it('surfaces hard constraints as risk indicators on Preflight', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({
      data: {
        ...validDecision,
        hard_constraints_applied: [
          {
            constraint: 'sparse_palette',
            description: 'Palette ≤ 2 — algo remplacé',
            forbidden_algorithms: [],
          },
        ],
      },
    })
    const wrapper = mountModal({ availableColorsCount: 2 })
    const next = () =>
      wrapper.findAll('button').find((b) => b.text() === 'Suivant')!
    // Walk all the way to Preflight.
    for (let i = 0; i < 5; i++) {
      await next().trigger('click')
      await nextTick()
    }
    expect(wrapper.find('[data-test="risk-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="risk-list"]').text()).toContain(
      'algo remplacé',
    )
  })

  it('emits cancel on the close button', async () => {
    const wrapper = mountModal()
    await wrapper.find('button[aria-label="Fermer"]').trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
  })

  it('falls back gracefully when the resolver errors out', async () => {
    vi.mocked(api.post).mockRejectedValueOnce(new Error('500 oops'))
    const wrapper = mountModal()
    const next = () =>
      wrapper.findAll('button').find((b) => b.text() === 'Suivant')!
    await next().trigger('click') // Source -> Intent
    await next().trigger('click') // Intent -> Algorithm
    await nextTick()
    await nextTick()
    expect(wrapper.text()).toContain('Erreur resolver')
  })

  it('shows a no-placement notice + locks Generate when no source is attached', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: validDecision })
    const wrapper = mountModal() // no sourceName, no previewSvg
    expect(wrapper.find('[data-test="modal-v2-no-placement"]').exists()).toBe(true)
    // Walk to Preflight where Generate lives.
    const next = () =>
      wrapper.findAll('button').find((b) => b.text() === 'Suivant')!
    for (let i = 0; i < 5; i++) {
      await next().trigger('click')
      await nextTick()
    }
    const confirm = wrapper.find('[data-test="confirm-button"]')
    expect(confirm.exists()).toBe(true)
    expect((confirm.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('hides the no-placement notice when a source is attached', () => {
    const wrapper = mountModal({
      sourceName: 'photo.jpg',
      previewSvg: '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
    })
    expect(wrapper.find('[data-test="modal-v2-no-placement"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="modal-v2-context"]').exists()).toBe(true)
  })

  it('emits open-v1 when the operator clicks the escape button', async () => {
    const wrapper = mountModal()
    await wrapper.find('[data-test="modal-v2-open-v1"]').trigger('click')
    expect(wrapper.emitted('open-v1')).toBeTruthy()
  })

  it('backdrop click emits cancel', async () => {
    const wrapper = mountModal()
    await wrapper.find('[data-test="modal-v2-backdrop"]').trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
  })

  it('Escape key emits cancel (accessibility)', async () => {
    const wrapper = mountModal({ attachTo: document.body })
    const event = new KeyboardEvent('keydown', { key: 'Escape' })
    window.dispatchEvent(event)
    await nextTick()
    expect(wrapper.emitted('cancel')).toBeTruthy()
    wrapper.unmount()
  })
})
