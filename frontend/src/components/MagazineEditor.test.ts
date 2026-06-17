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
const measureSpy = vi.hoisted(() => vi.fn())

vi.mock('../api/client', async (importActual) => {
  const actual = await importActual<typeof import('../api/client')>()
  return { ...actual, measureTipOffset: measureSpy, resetTipCalibration: vi.fn() }
})

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
        pen_lift_time_ms: 0,
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
        titleMono: 'Pen colour',
        titleManual: 'Pen colours',
        monoHint: 'mono hint',
        hintManual: 'manual hint',
        noProfile: 'No profile',
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
        applyOffsets: 'Per-pen tip offsets',
        applyOffsetsHint: 'offset hint',
        offsetX: 'Offset X',
        offsetY: 'Offset Y',
        offsetHint: 'relative to reference',
        useStation: 'Measure with a camera station',
        cameraUrl: 'Camera URL',
        mmPerPixel: 'mm per pixel',
        referenceSlot: 'Reference slot',
        stationHint: 'station hint',
        resetMeasurements: 'Reset measurements',
        measure: 'Measure',
        measuring: 'Measuring…',
        measureRefDone: 'Reference set',
        measureApplied: 'Offset {x}, {y} mm applied',
        measureNotFound: 'No tip detected',
        measureNeedRef: 'Measure the reference pen first',
        measureFailed: 'Measurement failed',
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
    measureSpy.mockReset()
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

  it('shows a colour list without calibration for manual mode', async () => {
    // Default profile is manual_pause → colour list, no physical magazine.
    const wrapper = mountEditor()
    await nextTick()
    expect(wrapper.find('[data-test="magazine-mono"]').exists()).toBe(false)
    // Per-slot colour selects are present, but no calibration block.
    expect(wrapper.findAll('select').length).toBeGreaterThanOrEqual(2)
    expect(wrapper.find('[data-test="pen-calibration-0"]').exists()).toBe(false)
  })

  it('shows a single colour editor for mono mode', async () => {
    const job = useJobStore()
    job.profiles[0]!.tool_change_method = 'none'
    job.profiles[0]!.pen_slot_count = 1
    const wrapper = mountEditor()
    await nextTick()
    expect(wrapper.find('[data-test="magazine-mono"]').exists()).toBe(true)
    // No per-slot calibration, no full slot list.
    expect(wrapper.find('[data-test="pen-calibration-0"]').exists()).toBe(false)
  })

  it('shows the full magazine (slots + calibration) for a host (rack) magazine', async () => {
    useJobStore().profiles[0]!.tool_change_method = 'rack'
    const wrapper = mountEditor()
    await nextTick()
    expect(wrapper.find('[data-test="magazine-mono"]').exists()).toBe(false)
    expect(wrapper.findAll('select').length).toBeGreaterThanOrEqual(2)
    expect(wrapper.find('[data-test="pen-calibration-0"]').exists()).toBe(true)
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

  it('keeps tip offsets opt-in: toggle off by default, no offset inputs', async () => {
    useJobStore().profiles[0]!.tool_change_method = 'rack'
    const wrapper = mountEditor()
    await nextTick()

    const toggle = wrapper.find('[data-test="apply-pen-offsets"]')
    expect(toggle.exists()).toBe(true)
    expect((toggle.element as HTMLInputElement).checked).toBe(false)
    // The per-slot offset inputs stay hidden until the operator opts in.
    expect(wrapper.find('[data-test="pen-offset-x-0"]').exists()).toBe(false)
  })

  it('enables offsets and saves a per-slot XY offset with manual provenance', async () => {
    useJobStore().profiles[0]!.tool_change_method = 'rack'
    const wrapper = mountEditor()
    await nextTick()

    // Opt in → the flag is persisted on the profile.
    const toggle = wrapper.find('[data-test="apply-pen-offsets"]')
    await toggle.setValue(true)
    await toggle.trigger('change')
    await nextTick()
    let saved = saveSpy.mock.calls.at(-1)![0] as MachineProfile
    expect(saved.apply_pen_offsets).toBe(true)

    // The offset inputs are now visible; set slot 0's X offset.
    const xInput = wrapper.find('[data-test="pen-offset-x-0"]')
    expect(xInput.exists()).toBe(true)
    await xInput.setValue('1.25')
    await xInput.trigger('change')
    await nextTick()
    saved = saveSpy.mock.calls.at(-1)![0] as MachineProfile
    const pen0 = saved.pens?.find((p) => p.index === 0)
    expect(pen0?.xy_offset_mm).toEqual({ x: 1.25, y: 0 })
    expect(pen0?.offset_source).toBe('manual')
  })

  it('hides Measure buttons until a camera station is configured', async () => {
    const job = useJobStore()
    job.profiles[0]!.tool_change_method = 'rack'
    job.profiles[0]!.apply_pen_offsets = true
    const wrapper = mountEditor()
    await nextTick()
    // Offsets on but no tip_calibration → no per-slot Measure button.
    expect(wrapper.find('[data-test="pen-measure-1"]').exists()).toBe(false)
    // The station toggle is offered so the operator can turn it on.
    expect(wrapper.find('[data-test="use-tip-station"]').exists()).toBe(true)
  })

  it('measures a tip and applies the offset with vision provenance', async () => {
    const job = useJobStore()
    job.profiles[0]!.tool_change_method = 'rack'
    job.profiles[0]!.apply_pen_offsets = true
    job.profiles[0]!.tip_calibration = {
      camera_url: 'cam://x',
      reference_slot: 0,
      mm_per_pixel: 0.1,
      detector: 'dark_blob',
      dark_threshold: 80,
      roi: null,
    }
    measureSpy.mockResolvedValue({
      found: true,
      slot: 1,
      is_reference: false,
      tip_px: { x: 130, y: 100 },
      confidence: 0.9,
      reference_measured: true,
      offset_mm: { x: 1.8, y: -0.5 },
      message: 'ok',
    })

    const wrapper = mountEditor()
    await nextTick()

    const btn = wrapper.find('[data-test="pen-measure-1"]')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await nextTick()
    await nextTick()

    expect(measureSpy).toHaveBeenCalledWith(
      expect.objectContaining({ slot: 1, camera_url: 'cam://x', reference_slot: 0 }),
    )
    const saved = saveSpy.mock.calls.at(-1)![0] as MachineProfile
    const pen1 = saved.pens?.find((p) => p.index === 1)
    expect(pen1?.xy_offset_mm).toEqual({ x: 1.8, y: -0.5 })
    expect(pen1?.offset_source).toBe('vision')
  })

  it('passes guided travel when auto-move is enabled and a station is set', async () => {
    const job = useJobStore()
    job.profiles[0]!.tool_change_method = 'rack'
    job.profiles[0]!.apply_pen_offsets = true
    job.profiles[0]!.tip_calibration = {
      camera_url: 'cam://x',
      reference_slot: 0,
      mm_per_pixel: 0.1,
      detector: 'dark_blob',
      dark_threshold: 80,
      roi: null,
      station_position: { x: 20, y: 30 },
    }
    measureSpy.mockResolvedValue({
      found: true,
      slot: 0,
      is_reference: true,
      tip_px: { x: 100, y: 100 },
      confidence: 0.9,
      reference_measured: true,
      offset_mm: { x: 0, y: 0 },
      message: 'ok',
    })

    const wrapper = mountEditor()
    await nextTick()

    // Enable the (now available) auto-move toggle, then measure.
    const autoMove = wrapper.find('[data-test="tip-auto-move"]')
    await autoMove.setValue(true)
    await wrapper.find('[data-test="pen-measure-0"]').trigger('click')
    await nextTick()
    await nextTick()

    expect(measureSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        slot: 0,
        move_to_station: true,
        station_position: { x: 20, y: 30 },
        profile_name: 'P',
      }),
    )
  })

  it('passes fetch_pen when the load-from-magazine toggle is on', async () => {
    const job = useJobStore()
    job.profiles[0]!.tool_change_method = 'rack'
    job.profiles[0]!.apply_pen_offsets = true
    job.profiles[0]!.tip_calibration = {
      camera_url: 'cam://x',
      reference_slot: 0,
      mm_per_pixel: 0.1,
      detector: 'dark_blob',
      dark_threshold: 80,
      roi: null,
    }
    measureSpy.mockResolvedValue({
      found: true,
      slot: 1,
      is_reference: false,
      tip_px: { x: 130, y: 100 },
      confidence: 0.9,
      reference_measured: true,
      offset_mm: { x: 1.8, y: 0 },
      message: 'ok',
    })

    const wrapper = mountEditor()
    await nextTick()

    await wrapper.find('[data-test="tip-fetch-pen"]').setValue(true)
    await wrapper.find('[data-test="pen-measure-1"]').trigger('click')
    await nextTick()
    await nextTick()

    expect(measureSpy).toHaveBeenCalledWith(
      expect.objectContaining({ slot: 1, fetch_pen: true, profile_name: 'P' }),
    )
  })

  it('reports a failed detection without applying an offset', async () => {
    const job = useJobStore()
    job.profiles[0]!.tool_change_method = 'rack'
    job.profiles[0]!.apply_pen_offsets = true
    job.profiles[0]!.tip_calibration = {
      camera_url: 'cam://x',
      reference_slot: 0,
      mm_per_pixel: 0.1,
      detector: 'dark_blob',
      dark_threshold: 80,
      roi: null,
    }
    measureSpy.mockResolvedValue({
      found: false,
      slot: 1,
      is_reference: false,
      tip_px: null,
      confidence: 0,
      reference_measured: false,
      offset_mm: null,
      message: 'no tip',
    })

    const wrapper = mountEditor()
    await nextTick()
    saveSpy.mockClear()

    await wrapper.find('[data-test="pen-measure-1"]').trigger('click')
    await nextTick()
    await nextTick()

    // Nothing persisted, and the operator sees the feedback message.
    expect(saveSpy).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="pen-measure-msg-1"]').text()).toBeTruthy()
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
