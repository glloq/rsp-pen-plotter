// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import MagazineEditor from './MagazineEditor.vue'
import { useAvailableColorsStore } from '../stores/availableColors'
import { useJobStore } from '../stores/job'
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
        noMagazine: { mono: 'mono — no magazine', manual: 'manual — no magazine' },
        hint: 'hint',
        slotCount: 'Slots',
        empty: 'empty',
        customColor: 'Custom {hex}',
        noAvailable: 'No colours',
        calibration: 'Calibration',
        posX: 'Slot X',
        posY: 'Slot Y',
        penUpOverride: 'Pen-up override',
        penDownOverride: 'Pen-down override',
        useProfileDefault: 'Profile default',
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
    // A magazine mode is required for the slot editor to render.
    useJobStore().profiles[0]!.tool_change_method = 'carousel'
    const colors = useAvailableColorsStore()
    colors.colors = [
      {
        color_id: 'r',
        hex: '#ff0000',
        name: 'Red',
        position: 0,
        stroke_width_mm: 0.5,
        odometer_mm: 0,
        created_at: '2026-01-01T00:00:00Z',
      },
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

  it('hides the whole magazine for manual / mono machines, showing a note', async () => {
    // Default profile is manual_pause → no physical magazine.
    const wrapper = mountEditor()
    await nextTick()
    expect(wrapper.find('[data-test="magazine-none"]').exists()).toBe(true)
    // No slot list (hence no per-slot colour select or calibration block).
    expect(wrapper.findAll('select')).toHaveLength(0)
    expect(wrapper.find('[data-test="pen-calibration-0"]').exists()).toBe(false)
  })

  it('shows the magazine slot list for a host (rack) magazine', async () => {
    useJobStore().profiles[0]!.tool_change_method = 'rack'
    const wrapper = mountEditor()
    await nextTick()
    expect(wrapper.find('[data-test="magazine-none"]').exists()).toBe(false)
    // Two slots → two colour selects.
    expect(wrapper.findAll('select').length).toBeGreaterThanOrEqual(2)
  })

  it('exposes per-slot calibration for carousel machines and saves a position', async () => {
    const job = useJobStore()
    job.profiles[0]!.tool_change_method = 'carousel'

    const wrapper = mountEditor()
    await nextTick()

    const block = wrapper.find('[data-test="pen-calibration-0"]')
    expect(block.exists()).toBe(true)

    // The first number input inside the calibration block is Slot X.
    const xInput = block.findAll('input[type="number"]')[0]!
    await xInput.setValue('42')
    await xInput.trigger('change')
    await nextTick()

    expect(saveSpy).toHaveBeenCalled()
    const saved = saveSpy.mock.calls.at(-1)![0] as MachineProfile
    expect(saved.pens?.find((p) => p.index === 0)?.position).toEqual({ x: 42, y: 0 })
  })

  it('saves a per-slot pen-up override and clears it back to null', async () => {
    const job = useJobStore()
    job.profiles[0]!.tool_change_method = 'carousel'

    const wrapper = mountEditor()
    await nextTick()

    const block = wrapper.find('[data-test="pen-calibration-0"]')
    const upInput = block.findAll('input[type="text"]')[0]!
    await upInput.setValue('M280 P0 S30')
    await upInput.trigger('change')
    await nextTick()
    let saved = saveSpy.mock.calls.at(-1)![0] as MachineProfile
    expect(saved.pens?.find((p) => p.index === 0)?.pen_up_command).toBe('M280 P0 S30')

    await upInput.setValue('   ')
    await upInput.trigger('change')
    await nextTick()
    saved = saveSpy.mock.calls.at(-1)![0] as MachineProfile
    expect(saved.pens?.find((p) => p.index === 0)?.pen_up_command).toBeNull()
  })
})
