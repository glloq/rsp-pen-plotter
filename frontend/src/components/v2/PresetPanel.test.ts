// @vitest-environment happy-dom
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createI18n } from 'vue-i18n'

vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client')
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
    getPresets: vi.fn(),
    saveUserPreset: vi.fn(),
    deleteUserPreset: vi.fn(),
  }
})

import * as client from '../../api/client'
import PresetPanel from './PresetPanel.vue'
import { useJobStore } from '../../stores/job'

const i18n = createI18n({
  legacy: false,
  locale: 'fr',
  fallbackLocale: 'fr',
  messages: {
    fr: {
      presets: {
        title: 'Préréglages',
        hint: 'Réutilise un précédent réglage.',
        namePlaceholder: 'Nom',
        descPlaceholder: 'Description',
        save: 'Enregistrer',
        saving: 'Enregistrement…',
        savedToast: 'Enregistré',
        deletedToast: 'Supprimé « {name} »',
        appliedToast: 'Appliqué « {name} »',
        builtin: 'Intégrés',
        user: 'Mes préréglages',
        delete: 'Supprimer',
        deleteFor: 'Supprimer {name}',
        empty: 'Aucun préréglage.',
        nothingToSave: 'Rien à enregistrer.',
      },
    },
  },
})

function mountPanel() {
  return mount(PresetPanel, { global: { plugins: [i18n] } })
}

describe('PresetPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(client.saveUserPreset).mockReset()
    vi.mocked(client.deleteUserPreset).mockReset()
    vi.mocked(client.getPresets).mockReset()
  })

  it('shows a no-op explainer when no placement / no captureable options', () => {
    const wrapper = mountPanel()
    expect(wrapper.find('[data-test="preset-panel-noop"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="preset-panel-save"]').exists()).toBe(false)
  })

  it('shows the save form once the placement has layer_algorithms set', async () => {
    const job = useJobStore()
    // Seed the store with a placement carrying a per-layer algorithm
    // override. The audit-fix path falls back to synthesising the save
    // snapshot from ``layer_algorithms`` when ``last_options`` is empty.
    job.placements = [
      {
        id: 'p1',
        library_file_id: null,
        sheet_id: null,
        upload_warnings: [],
        upload_metadata: {},
        layers: [{ layer_id: 'color-ff0000' }] as unknown as never,
        variants: [],
        active_variant_id: null,
        is_library_draft: false,
        layer_algorithms: { 'color-ff0000': { algorithm: 'stippling', algorithm_options: {} } },
        visibility: {},
        last_options: undefined,
        last_file: null,
        rerenderable: true,
      } as unknown as never,
    ]
    job.selectedPlacementId = 'p1'
    const wrapper = mountPanel()
    expect(wrapper.find('[data-test="preset-panel-save"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="preset-panel-noop"]').exists()).toBe(false)
  })

  it('renders builtin and user presets and only shows a delete button on user rows', async () => {
    const job = useJobStore()
    job.presets = [
      { name: 'Halftone', description: '', options: {}, kind: 'builtin' },
      { name: 'My fav', description: '', options: {}, kind: 'user' },
    ]
    const wrapper = mountPanel()
    expect(wrapper.find('[data-test="preset-chip-Halftone"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="preset-chip-My fav"]').exists()).toBe(true)
    // Built-in rows must not expose a delete affordance — the server
    // would reject it with 404 anyway, but the UI should reflect that
    // contract up front.
    expect(wrapper.find('[data-test="preset-delete-Halftone"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="preset-delete-My fav"]').exists()).toBe(true)
  })

  it('applies a preset to every layer of the current placement and rerenders', async () => {
    const job = useJobStore()
    job.placements = [
      {
        id: 'p1',
        library_file_id: null,
        sheet_id: null,
        upload_warnings: [],
        upload_metadata: {},
        layers: [
          { layer_id: 'color-aaa' },
          { layer_id: 'color-bbb' },
        ] as unknown as never,
        variants: [],
        active_variant_id: null,
        is_library_draft: false,
        layer_algorithms: {},
        visibility: {},
        last_options: undefined,
        last_file: null,
        rerenderable: true,
      } as unknown as never,
    ]
    job.selectedPlacementId = 'p1'
    job.presets = [
      {
        name: 'Stippling',
        description: '',
        options: { algorithm: 'stippling', algorithm_options: { density: 0.05 } },
        kind: 'builtin',
      },
    ]
    const applySpy = vi.spyOn(job, 'applyAlgorithmToAllLayers').mockResolvedValue()
    const wrapper = mountPanel()
    await wrapper.find('[data-test="preset-chip-Stippling"]').trigger('click')
    await flushPromises()
    expect(applySpy).toHaveBeenCalledWith('stippling', { density: 0.05 })
    expect(job.selectedPresetName).toBe('Stippling')
  })
})
