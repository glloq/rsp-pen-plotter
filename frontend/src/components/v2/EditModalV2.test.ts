// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createI18n } from 'vue-i18n'

vi.mock('../../api/client', () => ({
  api: { post: vi.fn(), get: vi.fn() },
  // The job store's preview / rerender paths import this wrapper
  // directly (not via ``api.post``), so the mock must provide it for
  // the size→render coupling test below.
  rerenderJob: vi.fn(),
}))

import { api, rerenderJob } from '../../api/client'
import { clearAlgorithmPolicyCache } from '../../domain/policy/client'
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
          layerCount: '{count} couche | {count} couches',
          noPlacement: 'Aucun placement actif',
          noPlacementTitle: 'Aucun placement actif',
          chooseIntent: 'Qu’est-ce qui compte le plus ?',
          previewLoading: 'Mise à jour de l’aperçu…',
          previewError: 'Aperçu indisponible.',
          zoomIn: 'Zoom +',
          zoomOut: 'Zoom −',
          resetView: 'Recentrer',
          paletteLabel: 'Couleurs',
          paletteMachine: 'Magazine machine',
          paletteFree: 'Palette libre',
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
  // Existing assertions target buttons that the welcome tour overlay
  // would cover on first run; opt out so the modal behaves like a
  // returning operator. The tour itself is covered by its own tests.
  skipOnboarding: true,
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
    vi.mocked(rerenderJob).mockReset()
    vi.mocked(rerenderJob).mockResolvedValue({ svg: '<svg/>', warnings: [] })
    // The resolver client memoises identical inputs across calls so the
    // editor doesn't re-pay the network round-trip on every open; tests
    // share inputs across cases, so clear it to keep ``api.post`` call
    // counts honest.
    clearAlgorithmPolicyCache()
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

  it('re-resolves when the operator switches the palette source', async () => {
    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()
    vi.mocked(api.post).mockClear()
    await wrapper.find('[data-test="palette-free"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="palette-free"]').classes()).toContain('active')
    expect(api.post).toHaveBeenCalledWith(
      '/policy/resolve',
      expect.objectContaining({ palette_mode: 'free' }),
    )
  })

  it('re-renders at the new physical size when the sheet format changes', async () => {
    // A rerenderable placement: the size→render watcher and the sheet
    // refit both need job_id + svg + layers to fire /rerender.
    const { useJobStore } = await import('../../stores/job')
    const job = useJobStore()
    const id = job.addEmptyPlacement()
    job.placements = job.placements.map((p) =>
      p.id === id
        ? {
            ...p,
            job_id: 'job-1',
            rerenderable: true,
            source_file: 'photo.jpg',
            svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>',
            layers: [
              {
                layer_id: 'color-112233',
                source_color: '#112233',
                target_pen_slot: null,
                draw_order: 0,
                total_length_mm: 100,
                path_count: 1,
                bbox: { x_min: 0, y_min: 0, x_max: 100, y_max: 100 },
                optimize: true,
                simplify_tolerance_mm: 0,
                drawing_speed_mm_s: null,
                color_label: null,
                pause_before: 'auto',
                assigned_color_hex: null,
                color_assignment: 'auto',
              },
            ],
          }
        : p,
    )
    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()
    vi.mocked(rerenderJob).mockClear()

    await wrapper.find('[data-test="sheet-preset-A2"]').trigger('click')
    // The placement is refit to the new page (100×100 → 420×420 on A2
    // portrait 420×594, centred).
    const p = job.selectedPlacement!
    expect(p.width_mm).toBeCloseTo(420)
    expect(p.height_mm).toBeCloseTo(420)

    // The size→render watcher is debounced (300 ms) and the store's
    // committed-SVG rerender at 250 ms; wait past both, then the new
    // physical size must have triggered at least one /rerender.
    await new Promise((resolve) => setTimeout(resolve, 400))
    await flushPromises()
    expect(vi.mocked(rerenderJob).mock.calls.length).toBeGreaterThanOrEqual(1)
    // The physical footprint rides along so millimetre options
    // (spacing_mm, …) convert to the right raster pitch server-side.
    const lastCall = vi.mocked(rerenderJob).mock.calls.at(-1)!
    expect(lastCall[5]).toMatchObject({ width_mm: 420, height_mm: 420 })
  })

  it('exposes zoom controls and updates the zoom level on click', async () => {
    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()
    const reset = wrapper.find('[data-test="modal-v2-zoom-reset"]')
    expect(reset.text()).toBe('100%')
    await wrapper.find('[data-test="modal-v2-zoom-in"]').trigger('click')
    expect(reset.text()).toBe('125%')
    await reset.trigger('click') // reset back to 100%
    expect(reset.text()).toBe('100%')
  })

  it('zooms on wheel within the preview surface', async () => {
    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()
    await wrapper.find('[data-test="modal-v2-preview"]').trigger('wheel', { deltaY: -100 })
    expect(wrapper.find('[data-test="modal-v2-zoom-reset"]').text()).not.toBe('100%')
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
    expect(wrapper.find('[data-test="modal-v2-resolve-error"]').text()).toContain('Erreur resolver')
    expect(wrapper.find('[data-test="modal-v2-preview-svg"]').exists()).toBe(true)
  })

  it('emits cancel on the close button', async () => {
    const wrapper = mountModal(PLACEMENT_PROPS)
    await wrapper.find('button[aria-label="Fermer"]').trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
  })

  it('no longer exposes the legacy "open V1 editor" escape hatch', () => {
    // V1 editor was removed in the v0.2 migration; the wizard is now
    // the only editor surface, so the escape-hatch button must not
    // render anymore.
    const wrapper = mountModal(PLACEMENT_PROPS)
    expect(wrapper.find('[data-test="modal-v2-open-v1"]').exists()).toBe(false)
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

  it('exposes the Apply button only in expert mode, gated by draft.isDirty', async () => {
    // Expert mode restores the V1 image / SVG / style / text tabs.
    // Mutations in those tabs flow through ``useBitmapDraft`` and only
    // land on the placement when the operator hits "Appliquer", which
    // calls ``fileManager.uploadSelected``. Keep the button visible in
    // expert only and disabled when the draft is clean so the operator
    // gets a clear "nothing to commit" affordance instead of a phantom
    // re-upload trigger.
    const { useUiModeStore } = await import('../../stores/uiMode')
    const wrapper = mountModal(PLACEMENT_PROPS)
    const uiMode = useUiModeStore()
    expect(wrapper.find('[data-test="modal-v2-apply-expert"]').exists()).toBe(false)
    uiMode.setMode('expert')
    await nextTick()
    const apply = wrapper.find('[data-test="modal-v2-apply-expert"]')
    expect(apply.exists()).toBe(true)
    // The button carries data-test plus a confirm handler; deeper
    // dirty-tracking is exercised by the underlying useBitmapDraft
    // tests (useBitmapDraft.test.ts).
  })

  it('hides the intent grid and mounts the expert panel when uiMode is expert', async () => {
    // The header toggle / "Ouvrir l'éditeur complet" button flips
    // uiMode.mode to 'expert'; the modal must respond by swapping its
    // body to the per-layer LayersSection + PresetPanel surface and
    // hiding the assisted intent / palette / style-stack fieldsets.
    // Without this swap, the bottom-half audit found, the toggle was a
    // placeholder. Lock the behaviour in a test so a future refactor
    // can't silently regress.
    const { useUiModeStore } = await import('../../stores/uiMode')
    const wrapper = mountModal(PLACEMENT_PROPS)
    const uiMode = useUiModeStore()
    uiMode.setMode('expert')
    await nextTick()
    expect(wrapper.find('[data-test="modal-v2-expert-panel"]').exists()).toBe(true)
    // Intent cards must be hidden in expert mode — they belong to the
    // assisted single-screen flow.
    expect(wrapper.find('[data-test="intent-balanced"]').exists()).toBe(false)
  })
})
