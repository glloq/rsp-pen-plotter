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
  // The palette-source store persists through these wrappers and
  // REVERTS its optimistic value when the call throws — they must
  // resolve for the "Palette libre → available" test to observe the
  // new source.
  getPaletteSource: vi.fn().mockResolvedValue({ source: 'pens' }),
  setPaletteSource: vi.fn().mockResolvedValue(undefined),
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
          saveStyle: 'Enregistrer le style',
          saveStyleHint: 'Enregistre le style',
          applyExpert: 'Appliquer',
          applyExpertHint: 'Reconvertit le fichier.',
          applyExpertClean: 'Aucun changement à appliquer.',
          applyError: "Impossible d'appliquer vos réglages expert : {message}.",
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
    // Start from the legacy ``pens`` source so the modal opens in
    // machine_only and clicking "free" is an actual switch (the global
    // default is now ``union`` → the modal would open in free already).
    const { usePaletteSourceStore } = await import('../../stores/paletteSource')
    usePaletteSourceStore().source = 'pens'
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

  it('re-segments against the operator palette when the decision wants fixed_palette', async () => {
    // 6 colours in the inventory + palette source "union": the resolver
    // decision (fixed_palette) must trigger a re-conversion against
    // those 6 colours — re-inking the original 4-cluster kmeans cache
    // collapsed most layers onto black ("I picked 6 colours, the
    // preview only shows one").
    const { useJobStore } = await import('../../stores/job')
    const { useAvailableColorsStore } = await import('../../stores/availableColors')
    const { usePaletteSourceStore } = await import('../../stores/paletteSource')
    const job = useJobStore()
    const palette = usePaletteSourceStore()
    palette.source = 'union'
    const inventory = useAvailableColorsStore()
    const hexes = ['#ff0000', '#00ff00', '#0000ff', '#ffff00', '#ff00ff', '#00ffff']
    inventory.colors = hexes.map((hex, i) => ({
      color_id: `id-${i}`,
      hex,
      name: `c${i}`,
      position: i,
      stroke_width_mm: 0.5,
      odometer_mm: 0,
      created_at: '',
    }))
    const id = job.addEmptyPlacement()
    const sourceFile = new File(['x'], 'photo.jpg', { type: 'image/jpeg' })
    job.placements = job.placements.map((p) =>
      p.id === id
        ? {
            ...p,
            source_file: 'photo.jpg',
            source_mime: 'image/jpeg',
            last_file: sourceFile,
            last_options: { segmentation_method: 'kmeans', num_colors: 4 },
          }
        : p,
    )
    const uploadSpy = vi.spyOn(job, 'upload').mockResolvedValue()

    mountModal(PLACEMENT_PROPS)
    await flushPromises()

    expect(uploadSpy).toHaveBeenCalledTimes(1)
    const [file, options] = uploadSpy.mock.calls[0]!
    // Vue's reactivity may hand back a proxy of the File; compare by
    // identity-relevant fields instead of reference.
    expect((file as File).name).toBe(sourceFile.name)
    // Perceptual clustering + ink remap (not fixed_palette): the
    // nearest-colour snap starved every saturated pen on
    // low-saturation photos, so adding inks changed nothing on screen.
    // num_colors = pool + 1: with drop_background (the default) the
    // paper-white background wins a cluster of its own before being
    // dropped — asking for exactly pool-size clusters silently cost
    // one ink ("6 couleurs dispo, 5 dessinées").
    expect(options).toMatchObject({
      segmentation_method: 'kmeans_lab',
      ink_pool: hexes,
      num_colors: 7,
    })
  })

  it('"Palette libre" points the pool at the inventory, not the pens∪inventory union', async () => {
    const { useAvailableColorsStore } = await import('../../stores/availableColors')
    const { usePaletteSourceStore } = await import('../../stores/paletteSource')
    const inventory = useAvailableColorsStore()
    inventory.colors = [
      {
        color_id: 'id-0',
        hex: '#ff0000',
        name: 'rouge',
        position: 0,
        stroke_width_mm: 0.5,
        odometer_mm: 0,
        created_at: '',
      },
    ]
    // Open from ``pens`` so clicking "free" is an actual switch (the
    // global default is now ``union`` → the modal opens in free mode).
    usePaletteSourceStore().source = 'pens'
    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()
    await wrapper.find('[data-test="palette-free"]').trigger('click')
    await flushPromises()
    expect(usePaletteSourceStore().source).toBe('available')
  })

  it('re-renders the adapted preview when a layer ink assignment changes', async () => {
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
    mountModal(PLACEMENT_PROPS)
    await flushPromises()
    vi.mocked(rerenderJob).mockClear()

    // The LayerCard picker path: assign an inventory ink to the layer.
    job.updateLayer('color-112233', { assigned_color_hex: '#ff0000', color_assignment: 'manual' })
    // Debounced watcher (300 ms) + the modal's adapted render.
    await new Promise((resolve) => setTimeout(resolve, 400))
    await flushPromises()
    const calls = vi.mocked(rerenderJob).mock.calls
    expect(calls.length).toBeGreaterThanOrEqual(1)
    // The adapted render ships the assignment as layer_ink_colors (5th arg).
    const inkArgs = calls.map((c) => c[4]).filter(Boolean)
    expect(inkArgs.some((m) => (m as Record<string, string>)['color-112233'] === '#ff0000')).toBe(
      true,
    )
  })

  it('skips the re-segmentation when the cache already matches the palette', async () => {
    const { useJobStore } = await import('../../stores/job')
    const { useAvailableColorsStore } = await import('../../stores/availableColors')
    const { usePaletteSourceStore } = await import('../../stores/paletteSource')
    const job = useJobStore()
    usePaletteSourceStore().source = 'union'
    const inventory = useAvailableColorsStore()
    const hexes = ['#ff0000', '#00ff00', '#0000ff']
    inventory.colors = hexes.map((hex, i) => ({
      color_id: `id-${i}`,
      hex,
      name: `c${i}`,
      position: i,
      stroke_width_mm: 0.5,
      odometer_mm: 0,
      created_at: '',
    }))
    const id = job.addEmptyPlacement()
    job.placements = job.placements.map((p) =>
      p.id === id
        ? {
            ...p,
            source_file: 'photo.jpg',
            source_mime: 'image/jpeg',
            last_file: new File(['x'], 'photo.jpg', { type: 'image/jpeg' }),
            last_options: {
              segmentation_method: 'kmeans_lab',
              ink_pool: hexes,
            },
          }
        : p,
    )
    const uploadSpy = vi.spyOn(job, 'upload').mockResolvedValue()

    mountModal(PLACEMENT_PROPS)
    await flushPromises()

    expect(uploadSpy).not.toHaveBeenCalled()
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

  // Focus-return-to-opener, Tab trapping, Shift+Tab, dynamic content and
  // aria-disabled/hidden filtering are covered deterministically in
  // useEditorDialogAccessibility.test.ts (the happy-dom focus model is
  // unreliable across a full Vue unmount, so those assertions live at the
  // composable level).

  it('exposes a single save button (no separate Apply) in both modes', async () => {
    // The footer's "Appliquer" + "Générer" pair collapsed into one header
    // "Enregistrer le style" button. In expert mode that single button
    // commits the dirty draft internally before emitting (the apply path
    // lives inside ``confirm`` now), so there's no standalone Apply button.
    const { useUiModeStore } = await import('../../stores/uiMode')
    const wrapper = mountModal(PLACEMENT_PROPS)
    const uiMode = useUiModeStore()
    // Assisted: one save button, no Apply button.
    expect(wrapper.find('[data-test="confirm-button"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="modal-v2-apply-expert"]').exists()).toBe(false)
    // Expert: still one save button, still no Apply button.
    uiMode.setMode('expert')
    await nextTick()
    expect(wrapper.find('[data-test="confirm-button"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="modal-v2-apply-expert"]').exists()).toBe(false)
  })

  it('toggles layer visibility from the ink chip eye', async () => {
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
    expect(job.isVisible('color-112233')).toBe(true)
    await wrapper.find('[data-test="modal-v2-ink-color-112233"]').trigger('click')
    // The eye writes straight to the visibility map — no rerender needed,
    // EditPreviewPane folds it into its opacity overlay.
    expect(job.isVisible('color-112233')).toBe(false)
  })

  it('offers the Text tab and a page navigator for a multi-page DOCX', async () => {
    // Regression: a DOCX (mixed text + image) opened with only the bitmap
    // tabs — no Text tab — and no way to switch pages. The Text tab is now
    // gated on ``fileManager.carriesText`` (true for PDF / DOCX / … as well
    // as .txt / .md) and the multi-page navigator reads ``page_count`` from
    // the upload metadata.
    const { useUiModeStore } = await import('../../stores/uiMode')
    const { useJobStore } = await import('../../stores/job')
    const { useFileManager } = await import('../../composables/useFileManager')
    const job = useJobStore()
    const id = job.addEmptyPlacement()
    job.placements = job.placements.map((p) =>
      p.id === id
        ? {
            ...p,
            job_id: 'job-doc',
            source_file: 'letter.docx',
            source_mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>',
            upload_metadata: { page_count: 3, page: 0 },
          }
        : p,
    )
    // The file-manager singleton leaks the previous test's File; pin the
    // active source so ``carriesText`` reads the DOCX extension rather than
    // a stale photo.jpg name.
    useFileManager().setFile(
      new File(['x'], 'letter.docx', {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      }),
    )
    const wrapper = mountModal({ ...PLACEMENT_PROPS, sourceName: 'letter.docx' })
    await flushPromises()

    // The page navigator surfaces in both modes (it lives in the preview
    // block, not the tab strip).
    expect(wrapper.find('[data-test="modal-v2-pages"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="modal-v2-page-prev"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="modal-v2-page-next"]').attributes('disabled')).toBeUndefined()

    // Expert mode reveals the tab strip; the Text tab must be present for
    // a text-bearing document.
    useUiModeStore().setMode('expert')
    await nextTick()
    const tabLabels = wrapper.findAll('[role="tab"]').map((b) => b.text())
    expect(tabLabels).toContain('editModal.tabText')
  })

  it('expert confirm waits for the draft upload before emitting confirm', async () => {
    // Race guard: in expert mode an operator who tweaked the image / SVG
    // / style tabs hits Generate expecting their changes to land in the
    // G-code. ``confirm`` must commit the dirty draft through
    // ``uploadSelected`` (→ ``job.upload``) and AWAIT it before emitting,
    // so the parent never generates from the pre-apply SVG. Drive
    // ``job.upload`` with a deferred promise to prove the ordering.
    const { useUiModeStore } = await import('../../stores/uiMode')
    const { useJobStore } = await import('../../stores/job')
    const { useBitmapDraft } = await import('../../composables/useBitmapDraft')
    const { useFileManager } = await import('../../composables/useFileManager')

    const job = useJobStore()
    let resolveUpload!: () => void
    const uploadSpy = vi.spyOn(job, 'upload').mockReturnValue(
      new Promise<void>((resolve) => {
        resolveUpload = resolve
      }),
    )

    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()

    useUiModeStore().setMode('expert')
    // Make the draft dirty + hand the file manager a source File so
    // ``uploadSelected`` proceeds past its ``_selectedFile`` guard. The
    // draft is a module singleton that leaks across tests, so pin a known
    // baseline first, then mutate it — that way "dirty" holds regardless
    // of what a prior test committed.
    const draft = useBitmapDraft()
    draft.markCommitted()
    draft.bitmap.value.preprocess.invert = !draft.bitmap.value.preprocess.invert
    useFileManager().setFile(new File(['x'], 'photo.jpg', { type: 'image/jpeg' }))
    await nextTick()

    await wrapper.find('[data-test="confirm-button"]').trigger('click')
    await flushPromises()

    // Upload is in flight → confirm must NOT have fired yet, and Generate
    // is locked so a second click can't race the re-upload.
    expect(uploadSpy).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('confirm')).toBeFalsy()
    const generate = wrapper.find('[data-test="confirm-button"]')
    expect((generate.element as HTMLButtonElement).disabled).toBe(true)

    resolveUpload()
    await flushPromises()

    // Only now, after the upload settled, does confirm emit.
    expect(wrapper.emitted('confirm')).toBeTruthy()
    expect((generate.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('expert confirm aborts (no emit, error shown) when the draft upload fails', async () => {
    const { useUiModeStore } = await import('../../stores/uiMode')
    const { useJobStore } = await import('../../stores/job')
    const { useBitmapDraft } = await import('../../composables/useBitmapDraft')
    const { useFileManager } = await import('../../composables/useFileManager')

    const job = useJobStore()
    vi.spyOn(job, 'upload').mockRejectedValue(new Error('network down'))

    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()

    useUiModeStore().setMode('expert')
    const draft = useBitmapDraft()
    draft.markCommitted()
    draft.bitmap.value.preprocess.invert = !draft.bitmap.value.preprocess.invert
    useFileManager().setFile(new File(['x'], 'photo.jpg', { type: 'image/jpeg' }))
    await nextTick()

    await wrapper.find('[data-test="confirm-button"]').trigger('click')
    await flushPromises()

    // A failed apply must block confirm and surface the reason, so a
    // network hiccup can never generate from un-applied changes.
    expect(wrapper.emitted('confirm')).toBeFalsy()
    const error = wrapper.find('[data-test="modal-v2-apply-error"]')
    expect(error.exists()).toBe(true)
    expect(error.text()).toContain('network down')
    // Generate is usable again so the operator can retry.
    expect(
      (wrapper.find('[data-test="confirm-button"]').element as HTMLButtonElement).disabled,
    ).toBe(false)
  })

  it('blocks closing while an expert apply is committing', async () => {
    // Closing mid-commit would let ``confirm`` emit after the modal is gone
    // (audit P1 §3). The close gate must swallow the close while the upload
    // is in flight.
    const { useUiModeStore } = await import('../../stores/uiMode')
    const { useJobStore } = await import('../../stores/job')
    const { useBitmapDraft } = await import('../../composables/useBitmapDraft')
    const { useFileManager } = await import('../../composables/useFileManager')

    const job = useJobStore()
    let resolveUpload!: () => void
    vi.spyOn(job, 'upload').mockReturnValue(
      new Promise<void>((resolve) => {
        resolveUpload = resolve
      }),
    )

    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()
    useUiModeStore().setMode('expert')
    const draft = useBitmapDraft()
    draft.markCommitted()
    draft.bitmap.value.preprocess.invert = !draft.bitmap.value.preprocess.invert
    useFileManager().setFile(new File(['x'], 'photo.jpg', { type: 'image/jpeg' }))
    await nextTick()

    // Kick off the commit, then try to close while it's in flight.
    await wrapper.find('[data-test="confirm-button"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="modal-v2-close"]').trigger('click')
    expect(wrapper.emitted('cancel')).toBeFalsy()

    resolveUpload()
    await flushPromises()
  })

  it('confirms before discarding an unsaved expert draft on close', async () => {
    const { useUiModeStore } = await import('../../stores/uiMode')
    const { useBitmapDraft } = await import('../../composables/useBitmapDraft')

    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()
    useUiModeStore().setMode('expert')
    const draft = useBitmapDraft()
    draft.markCommitted()
    draft.bitmap.value.preprocess.invert = !draft.bitmap.value.preprocess.invert
    await nextTick()

    // Decline the discard → modal stays open. (happy-dom has no native
    // ``window.confirm``; assign a mock rather than spying on undefined.)
    const confirmSpy = vi.fn().mockReturnValue(false)
    const originalConfirm = window.confirm
    window.confirm = confirmSpy as unknown as typeof window.confirm
    await wrapper.find('[data-test="modal-v2-close"]').trigger('click')
    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('cancel')).toBeFalsy()

    // Accept the discard → modal closes.
    confirmSpy.mockReturnValue(true)
    await wrapper.find('[data-test="modal-v2-close"]').trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
    window.confirm = originalConfirm
  })

  it('does not prompt on an assisted-mode close even though the shared draft reads dirty', async () => {
    // The bitmap draft is "dirty by default" until an upload pins its
    // baseline, but the assisted wizard never edits it — closing assisted
    // mode must never nag.
    const confirmSpy = vi.fn().mockReturnValue(false)
    const originalConfirm = window.confirm
    window.confirm = confirmSpy as unknown as typeof window.confirm
    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()
    await wrapper.find('[data-test="modal-v2-close"]').trigger('click')
    expect(confirmSpy).not.toHaveBeenCalled()
    expect(wrapper.emitted('cancel')).toBeTruthy()
    window.confirm = originalConfirm
  })

  it('warns before discarding an unsaved assisted style change on close', async () => {
    // The assisted preview is render-only: changing the intent (or the
    // custom-style stack) doesn't reach ``placement.svg`` until Save runs.
    // Closing without saving would silently drop the change and leave the
    // plan showing the old style, so the close gate must prompt first.
    const confirmSpy = vi.fn().mockReturnValue(false)
    const originalConfirm = window.confirm
    window.confirm = confirmSpy as unknown as typeof window.confirm
    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()

    // Change the assisted style without saving.
    await wrapper.find('[data-test="intent-fast"]').trigger('click')
    await flushPromises()

    // Decline the discard → modal stays open.
    await wrapper.find('[data-test="modal-v2-close"]').trigger('click')
    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('cancel')).toBeFalsy()

    // Accept the discard → modal closes.
    confirmSpy.mockReturnValue(true)
    await wrapper.find('[data-test="modal-v2-close"]').trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
    window.confirm = originalConfirm
  })

  it('hides the intent grid and mounts the expert panel when uiMode is expert', async () => {
    // The header toggle / "Ouvrir l'éditeur complet" button flips
    // uiMode.mode to 'expert'; the modal must respond by swapping its
    // body to the per-layer LayersSection tab surface and
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
    // The expert tab strip is async-loaded (defineAsyncComponent) to keep
    // it out of the assisted chunk; flush the dynamic import and confirm
    // it actually mounts rather than silently failing to resolve.
    await flushPromises()
    expect(wrapper.find('[role="tablist"]').exists()).toBe(true)
  })

  // ---- Assisted parcours (integration) ------------------------------------
  // End-to-end-ish coverage of the headline assisted flow the audit's
  // Phase 3 calls for, driven through the real modal + stores (the browser
  // E2E equivalent needs a backend + Playwright browser).

  it('full assisted parcours: pick intent, switch palette, then Generate emits the latest decision', async () => {
    const { usePaletteSourceStore } = await import('../../stores/paletteSource')
    usePaletteSourceStore().source = 'pens'
    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()

    // Pick the "fast" intent.
    await wrapper.find('[data-test="intent-fast"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="intent-fast"]').classes()).toContain('active')

    // Switch to the free palette.
    await wrapper.find('[data-test="palette-free"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="palette-free"]').classes()).toContain('active')

    // The last resolve must carry BOTH the chosen goal and palette.
    expect(api.post).toHaveBeenLastCalledWith(
      '/policy/resolve',
      expect.objectContaining({ goal: 'fast', palette_mode: 'free' }),
    )

    // Generate emits the resolved decision.
    const confirm = wrapper.find('[data-test="confirm-button"]')
    expect((confirm.element as HTMLButtonElement).disabled).toBe(false)
    await confirm.trigger('click')
    expect(wrapper.emitted('confirm')?.[0]?.[0]).toMatchObject({ default_algorithm: 'scanlines' })
  })

  it('rapid intent changes settle on the last choice (one decision generated)', async () => {
    const wrapper = mountModal(PLACEMENT_PROPS)
    await flushPromises()

    // Fire three intents back-to-back; each immediate schedule aborts the
    // previous in-flight flush, so the pipeline settles on the last one.
    await wrapper.find('[data-test="intent-fast"]').trigger('click')
    await wrapper.find('[data-test="intent-balanced"]').trigger('click')
    await wrapper.find('[data-test="intent-quality"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="intent-quality"]').classes()).toContain('active')
    expect(api.post).toHaveBeenLastCalledWith(
      '/policy/resolve',
      expect.objectContaining({ goal: 'quality' }),
    )
    // Generate is enabled and emits exactly once.
    await wrapper.find('[data-test="confirm-button"]').trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('Escape dismisses the welcome tour without closing the modal', async () => {
    // First-run tour (no skipOnboarding, fresh localStorage). Escape must
    // dismiss the tour and leave the modal open — the modal body is inert
    // while the tour shows, so a stray Escape shouldn't tear it all down.
    const wrapper = mountModal({
      sourceName: 'photo.jpg',
      previewSvg: '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
      attachTo: document.body,
    })
    await flushPromises()
    expect(wrapper.find('[data-test="modal-v2-tour"]').exists()).toBe(true)
    // The body is inert while the tour owns the foreground.
    expect(wrapper.find('[data-test="modal-v2-layout"]').attributes('inert')).toBeDefined()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()

    expect(wrapper.find('[data-test="modal-v2-tour"]').exists()).toBe(false)
    expect(wrapper.emitted('cancel')).toBeFalsy()
    // Body is interactive again.
    expect(wrapper.find('[data-test="modal-v2-layout"]').attributes('inert')).toBeUndefined()
    wrapper.unmount()
  })

  it('keeps Generate locked while the resolve is still in flight', async () => {
    // Hold the resolver so the pipeline stays in its non-terminal state;
    // Generate must stay disabled until the decision lands (audit P0 §2).
    let resolveResolve!: (v: unknown) => void
    vi.mocked(api.post).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveResolve = () => resolve({ data: validDecision })
        }),
    )
    const wrapper = mountModal(PLACEMENT_PROPS)
    await nextTick()

    const confirm = wrapper.find('[data-test="confirm-button"]')
    expect((confirm.element as HTMLButtonElement).disabled).toBe(true)

    resolveResolve({ data: validDecision })
    await flushPromises()
    expect((confirm.element as HTMLButtonElement).disabled).toBe(false)
  })
})
