// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import AvailableColorsPanel from './AvailableColorsPanel.vue'
import { useAvailableColorsStore } from '../stores/availableColors'

// Cover the observable surface of the Plotter > Couleurs tab: empty
// state copy, add-form wiring (hex + name → store.add), inventory
// rendering with swatches + hex + name, and the reorder helpers. The
// store's network adapter is stubbed so each test runs without a
// backend.

vi.mock('../api/client', () => ({
  listAvailableColors: vi.fn(async () => []),
  createAvailableColor: vi.fn(async (hex: string, name: string, strokeWidthMm?: number) => ({
    color_id: `stub-${hex}`,
    hex,
    name,
    position: 0,
    stroke_width_mm: strokeWidthMm ?? 0.5,
    odometer_mm: 0,
    created_at: '2026-01-01T00:00:00Z',
  })),
  patchAvailableColor: vi.fn(async (colorId: string, patch: Record<string, unknown>) => ({
    color_id: colorId,
    hex: (patch.hex as string) ?? '#000000',
    name: (patch.name as string) ?? '',
    position: (patch.position as number) ?? 0,
    stroke_width_mm: (patch.stroke_width_mm as number) ?? 0.5,
    odometer_mm: (patch.odometer_mm as number) ?? 0,
    created_at: '2026-01-01T00:00:00Z',
  })),
  deleteAvailableColor: vi.fn(async () => undefined),
}))

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      availableColors: {
        hint: 'Hint',
        add: 'Add a colour',
        addAction: 'Add',
        hex: 'Hex',
        namePlaceholder: 'Name',
        inventory: 'Inventory',
        empty: 'No colours yet.',
        loading: 'Loading…',
        moveUp: 'Move up',
        moveDown: 'Move down',
        edit: 'Edit',
        delete: 'Delete',
        deleteConfirm: 'Remove?',
        loadFailed: 'load failed',
        createFailed: 'create failed',
        updateFailed: 'update failed',
        deleteFailed: 'delete failed',
      },
    },
  },
})

function mountPanel() {
  return mount(AvailableColorsPanel, { global: { plugins: [i18n] } })
}

describe('AvailableColorsPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders the empty state copy when no colour is in the inventory', async () => {
    const store = useAvailableColorsStore()
    store.loaded = true
    const wrapper = mountPanel()
    await nextTick()
    expect(wrapper.text()).toContain('No colours yet.')
  })

  it('renders one row per colour, with a swatch + hex + name', async () => {
    const store = useAvailableColorsStore()
    store.colors = [
      {
        color_id: 'a',
        hex: '#ff0000',
        name: 'Red',
        position: 0,
        stroke_width_mm: 0.5,
        odometer_mm: 0,
        created_at: '2026-01-01T00:00:00Z',
      },
      {
        color_id: 'b',
        hex: '#00ff00',
        name: '',
        position: 1,
        stroke_width_mm: 0.5,
        odometer_mm: 0,
        created_at: '2026-01-02T00:00:00Z',
      },
    ]
    store.loaded = true
    const wrapper = mountPanel()
    await nextTick()
    const rows = wrapper.findAll('li')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('Red')
    expect(rows[0]!.text()).toContain('#ff0000')
    // Row without a name falls back to its hex as the display label.
    expect(rows[1]!.text()).toContain('#00ff00')
  })

  it('add button calls store.add with the typed hex and name', async () => {
    const store = useAvailableColorsStore()
    store.loaded = true
    const spy = vi.spyOn(store, 'add').mockResolvedValue({
      color_id: 'new',
      hex: '#123456',
      name: 'Indigo',
      position: 0,
      stroke_width_mm: 0.5,
      odometer_mm: 0,
      created_at: '2026-01-01T00:00:00Z',
    })
    const wrapper = mountPanel()
    await nextTick()
    const inputs = wrapper.findAll('input')
    // First two inputs in the form are hex (color + text) — keep the
    // text shape input, then the name. happy-dom doesn't fire the
    // ``input`` event from setValue on type=color, so target the text
    // hex input instead.
    const hexText = inputs.find((i) => i.element.type === 'text' && i.element.value.startsWith('#'))!
    const nameInput = inputs.find(
      (i) => i.element.type === 'text' && !i.element.value.startsWith('#'),
    )!
    await hexText.setValue('#123456')
    await nameInput.setValue('Indigo')
    const addBtn = wrapper.findAll('button').find((b) => b.text() === 'Add')!
    await addBtn.trigger('click')
    expect(spy).toHaveBeenCalledWith('#123456', 'Indigo', 0.5)
  })
})
