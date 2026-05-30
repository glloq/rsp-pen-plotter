// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import MagazineEditor from './MagazineEditor.vue'
import { useAvailableColorsStore } from '../stores/availableColors'
import type { MachineProfile } from '../api/client'

// Regression guard for the "assigned colour stays black" bug: the
// magazine's ``patchPen`` used ``structuredClone`` on the reactive
// profile proxy, which throws ``DataCloneError`` — so the save never
// ran and the slot kept its default black colour. The mocked job store
// below is a *real* Pinia store (so ``storeToRefs`` works) whose
// ``saveProfile`` mirrors the backend round-trip by replacing the
// selected profile with the persisted shape.

const saveSpy = vi.hoisted(() => vi.fn())

vi.mock('../stores/job', async () => {
  const { defineStore } = await import('pinia')
  const { ref, computed } = await import('vue')
  const useJobStore = defineStore('job', () => {
    const profiles = ref<MachineProfile[]>([
      {
        name: 'P',
        units: 'mm',
        workspace: { x_min: 0, y_min: 0, x_max: 297, y_max: 210 },
        origin: 'top_left',
        gcode_dialect: 'grbl',
        pen_up_command: 'M5',
        pen_down_command: 'M3',
        tool_change_method: 'manual_pause',
        tool_change_command: 'M0',
        drawing_speed_mm_s: 50,
        travel_speed_mm_s: 100,
        acceleration_mm_s2: 1000,
        pen_slot_count: 2,
        supports_arcs: false,
        arc_tolerance_mm: 0.1,
        ebb: null,
        pens: [
          {
            index: 0,
            name: 'Pen 0',
            color: '#000000',
            installed: true,
            position: null,
            pen_up_command: null,
            pen_down_command: null,
          },
          {
            index: 1,
            name: 'Pen 1',
            color: '#000000',
            installed: true,
            position: null,
            pen_up_command: null,
            pen_down_command: null,
          },
        ],
      },
    ])
    const selectedProfile = computed(() => profiles.value[0] ?? null)
    async function saveProfile(profile: MachineProfile): Promise<void> {
      saveSpy(profile)
      // Mirror the real store: reload swaps in the persisted profile so
      // the computed ``selectedProfile`` (and the swatch) reflect it.
      profiles.value = [profile]
    }
    return { profiles, selectedProfile, saveProfile }
  })
  return { useJobStore }
})

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      magazine: {
        title: 'Magazine',
        noProfile: 'No profile',
        hint: 'hint',
        slotCount: 'Slots',
        empty: 'empty',
        customColor: 'Custom {hex}',
        noAvailable: 'No colours',
      },
      availableColors: { pickColor: 'Pick' },
      colorPicker: { title: 'Colour', cancel: 'Cancel', confirm: 'OK' },
      profile: { installed: 'Installed', saveFailed: 'save failed' },
    },
  },
})

function mountEditor() {
  return mount(MagazineEditor, { global: { plugins: [i18n] } })
}

describe('MagazineEditor', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    saveSpy.mockClear()
  })

  it('persists an assigned available colour onto the pen slot', async () => {
    const colors = useAvailableColorsStore()
    colors.colors = [
      { color_id: 'r', hex: '#ff0000', name: 'Red', position: 0, stroke_width_mm: 0.5, odometer_mm: 0, created_at: '2026-01-01T00:00:00Z' },
    ]
    colors.loaded = true

    const wrapper = mountEditor()
    await nextTick()

    // First pen slot's colour dropdown — pick the available red.
    const select = wrapper.findAll('select')[0]!
    await select.setValue('#ff0000')
    await nextTick()

    // The save must actually fire (it threw before the fix) and carry
    // the new colour on slot 0...
    expect(saveSpy).toHaveBeenCalledTimes(1)
    const saved = saveSpy.mock.calls[0]![0] as MachineProfile
    expect(saved.pens?.find((p) => p.index === 0)?.color).toBe('#ff0000')

    // ...and the slot's swatch reflects it rather than staying black.
    const swatch = wrapper.findAll('button[title]').find((b) => b.attributes('title') === '#ff0000')
    expect(swatch).toBeDefined()
  })
})
