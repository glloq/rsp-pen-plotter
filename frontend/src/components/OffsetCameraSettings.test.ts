// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import OffsetCameraSettings from './OffsetCameraSettings.vue'
import { useJobStore } from '../stores/job'
import { useUiStore } from '../stores/ui'
import type { MachineProfile } from '../api/client'

const saveSpy = vi.hoisted(() => vi.fn())
const measureSpy = vi.hoisted(() => vi.fn())
const lightSpy = vi.hoisted(() => vi.fn())
const gpioSpy = vi.hoisted(() => vi.fn())
const scaleSpy = vi.hoisted(() => vi.fn())

vi.mock('../api/client', async (importActual) => {
  const actual = await importActual<typeof import('../api/client')>()
  return {
    ...actual,
    measureTipOffset: measureSpy,
    resetTipCalibration: vi.fn(),
    setTipLight: lightSpy,
    getTipGpio: gpioSpy,
    calibrateTipScale: scaleSpy,
  }
})

function blankPen(index: number) {
  return {
    index,
    name: `Pen ${index}`,
    color: '#000000',
    installed: true,
    position: null,
    pen_up_command: null,
    pen_down_command: null,
  }
}

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
        tool_change_method: 'rack',
        tool_change_command: 'M0',
        drawing_speed_mm_s: 50,
        travel_speed_mm_s: 100,
        acceleration_mm_s2: 1000,
        pen_lift_time_ms: 0,
        pen_slot_count: 2,
        supports_arcs: false,
        arc_tolerance_mm: 0.1,
        ebb: null,
        pens: [blankPen(0), blankPen(1)],
      },
    ])
    const selectedProfile = computed(() => profiles.value[0] ?? null)
    async function saveProfile(profile: MachineProfile): Promise<void> {
      saveSpy(profile)
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
      offsetCamera: {
        title: 'Offset camera',
        hint: 'hint',
        needsMagazine: 'needs magazine',
        manualModeOnlyDuringSwap: 'manual mode note',
        enable: 'Use a camera',
        step1: '1 Camera',
        step1Hint: 'point it',
        step2: '2 Scale',
        step2Hint: 'mm per pixel',
        step3: '3 Measure',
        step3Hint: 'reference first',
        advanced: 'Advanced',
        scaleSet: 'Scale {v}',
        scaleUnset: 'Scale not set',
        statusReference: 'Reference',
        statusMeasured: 'Measured',
        statusManual: 'Manual',
        statusPending: 'Not measured',
        manualPresent: 'present by hand',
        guidedStart: 'Guided measurement',
        guidedStartNext: 'Measure {pen}',
        guidedStartReview: 'Review measurements',
        measureButton: 'Measure',
        remeasureButton: 'Remeasure',
        guidedStep: 'Step {k}/{n} — {pen}',
        guidedPresent: 'Present {pen}',
        guidedMeasure: 'Measure this pen',
        guidedDone: 'Done',
        lowConfidence: 'Low confidence {c}%',
        testDetection: 'Test detection',
        testResult: 'Detected {c}%',
        samples: 'Frames to average',
        largeOffset: '⚠ large offset ({mm} mm)',
        repeatability: '(±{mm} mm)',
        unstable: '⚠ frames vary by {mm} mm',
        progress: '{k}/{n} measured',
        clearOffset: 'Clear',
        ready: {
          camera: 'Camera',
          scale: 'Scale',
          reference: 'Reference',
          zone: 'Zone',
          light: 'Light',
        },
        next: {
          camera: 'Next camera',
          scale: 'Next scale',
          reference: 'Next reference',
          ready: 'Ready to measure',
        },
        lightOnOk: 'Light on',
        lightOffOk: 'Light off',
        lightFailed: 'Light failed',
      },
      cameraPreview: { empty: 'no url', retry: 'retry', refresh: 'refresh' },
      magazine: {
        noProfile: 'No profile',
        saved: 'Saved',
        applyOffsets: 'Per-pen tip offsets',
        applyOffsetsHint: 'offset hint',
        offsetX: 'Offset X',
        offsetY: 'Offset Y',
        offsetHint: 'relative to reference',
        useStation: 'Measure with a camera station',
        offsetCamera: 'Offset camera',
        offsetCameraHint: 'dedicated',
        cameraCustom: 'Custom URL',
        cameraN: 'Camera {n}',
        mmPerPixel: 'mm per pixel',
        darkThreshold: 'Dark threshold',
        referenceSlot: 'Reference slot',
        stationX: 'Station X',
        stationY: 'Station Y',
        stationZ: 'Station Z',
        fetchPen: 'Fetch pen',
        autoMove: 'Move to station',
        roiTitle: 'Detection zone',
        roiClear: 'Clear',
        lightTitle: 'Light',
        lightGpioPin: 'GPIO pin',
        lightNoPin: 'none',
        lightActiveHigh: 'Active high',
        gpioUnavailable: 'GPIO unavailable',
        lightOn: 'On',
        lightOff: 'Off',
        lightDuringMeasure: 'Light during measure',
        resetMeasurements: 'Reset',
        scaleTitle: 'Scale',
        scaleHint: 'present a target',
        scaleKnownMm: 'Known mm',
        scaleMeasure: 'Measure scale',
        scaleApplied: 'Scale {v} ({px}px)',
        scaleNotFound: 'no target',
        scaleFailed: 'scale failed',
        measure: 'Measure',
        measuring: 'Measuring…',
        measureRefDone: 'Reference set',
        measureApplied: 'Offset {x}, {y} ({c}%)',
        measureNotFound: 'No tip detected',
        measureNeedRef: 'Measure reference first',
        measureFailed: 'Measurement failed',
        measurePreviewAlt: 'Detected tip',
      },
      profile: { saveFailed: 'save failed' },
    },
  },
})

function mountPanel() {
  return mount(OffsetCameraSettings, { global: { plugins: [i18n] } })
}

function withStation(extra: Record<string, unknown> = {}): void {
  const job = useJobStore()
  job.profiles[0]!.apply_pen_offsets = true
  job.profiles[0]!.tip_calibration = {
    camera_url: 'cam://x',
    reference_slot: 0,
    mm_per_pixel: 0.1,
    detector: 'dark_blob',
    dark_threshold: 80,
    roi: null,
    ...extra,
  }
  measureSpy.mockResolvedValue({
    found: true,
    slot: 1,
    is_reference: false,
    tip_px: { x: 130, y: 100 },
    confidence: 0.9,
    reference_measured: true,
    offset_mm: { x: 1, y: 0 },
    message: 'ok',
    annotated_image: null,
  })
}

describe('OffsetCameraSettings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    saveSpy.mockClear()
    measureSpy.mockReset()
    lightSpy.mockReset()
    gpioSpy.mockReset()
    gpioSpy.mockResolvedValue({ available: true, pins: [17, 18, 27] })
    scaleSpy.mockReset()
  })

  it('hides the feature for a single-pen profile', async () => {
    const job = useJobStore()
    job.profiles[0]!.pen_slot_count = 1
    job.profiles[0]!.pens = [blankPen(0)]
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.find('[data-test="apply-pen-offsets"]').exists()).toBe(false)
  })

  it('keeps offsets opt-in: toggle off by default, no offset inputs', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    const toggle = wrapper.find('[data-test="apply-pen-offsets"]')
    expect(toggle.exists()).toBe(true)
    expect((toggle.element as HTMLInputElement).checked).toBe(false)
    expect(wrapper.find('[data-test="pen-offset-x-0"]').exists()).toBe(false)
  })

  it('enables offsets and saves a per-slot XY offset (manual provenance)', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    const toggle = wrapper.find('[data-test="apply-pen-offsets"]')
    await toggle.setValue(true)
    await toggle.trigger('change')
    await nextTick()
    expect((saveSpy.mock.calls.at(-1)![0] as MachineProfile).apply_pen_offsets).toBe(true)

    const xInput = wrapper.find('[data-test="pen-offset-x-0"]')
    expect(xInput.exists()).toBe(true)
    await xInput.setValue('1.25')
    await xInput.trigger('change')
    await nextTick()
    const pen0 = (saveSpy.mock.calls.at(-1)![0] as MachineProfile).pens?.find((p) => p.index === 0)
    expect(pen0?.xy_offset_mm).toEqual({ x: 1.25, y: 0 })
    expect(pen0?.offset_source).toBe('manual')
  })

  it('shows a per-pen status badge (reference vs measured)', async () => {
    withStation()
    const job = useJobStore()
    // Slot 1 has a camera-measured offset; slot 0 is the reference.
    job.profiles[0]!.pens![1]!.offset_source = 'vision'
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.find('[data-test="offset-status-0"]').text()).toBe('Reference')
    expect(wrapper.find('[data-test="offset-status-1"]').text()).toBe('Measured')
  })

  it('hides independent camera measurements in manual pen-change mode', async () => {
    const job = useJobStore()
    job.profiles[0]!.tool_change_method = 'manual_pause'
    withStation()
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.find('[data-test="offset-manual-mode-note"]').text()).toContain(
      'manual mode note',
    )
    expect(wrapper.find('[data-test="tip-fetch-pen"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="manual-present-hint"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="pen-measure-1"]').exists()).toBe(false)
  })

  it('shows the auto-fetch toggle with a magazine (rack)', async () => {
    withStation() // mock profile is tool_change_method: 'rack'
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.find('[data-test="tip-fetch-pen"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="manual-present-hint"]').exists()).toBe(false)
  })

  it('guided sequence walks pens reference-first and advances on success', async () => {
    withStation() // reference_slot 0, station configured
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.find('[data-test="guide-start"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="guide-panel"]').exists()).toBe(true)
    // Step 1 = reference pen (slot 0).
    expect(wrapper.find('[data-test="guide-step"]').text()).toContain('1/2')

    await wrapper.find('[data-test="guide-measure"]').trigger('click')
    await flushPromises()
    // Advanced to slot 1.
    expect(wrapper.find('[data-test="guide-step"]').text()).toContain('2/2')

    await wrapper.find('[data-test="guide-measure"]').trigger('click')
    await flushPromises()
    // Sequence complete → wizard closed.
    expect(wrapper.find('[data-test="guide-panel"]').exists()).toBe(false)

    expect(measureSpy).toHaveBeenCalledTimes(2)
    expect(measureSpy.mock.calls[0]![0]).toMatchObject({ slot: 0 })
    expect(measureSpy.mock.calls[1]![0]).toMatchObject({ slot: 1 })
  })

  it('counts only actually measured pens and resumes the guide at the next pending pen', async () => {
    withStation()
    const job = useJobStore()
    job.profiles[0]!.pens![0]!.offset_source = 'vision'
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.find('[data-test="offset-progress"]').text()).toContain('1/2')
    expect(wrapper.find('[data-test="guide-start"]').text()).toContain('Measure Pen 1')

    await wrapper.find('[data-test="guide-start"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="guide-step"]').text()).toContain('2/2')
  })

  it('uses explicit measure and remeasure labels for per-pen actions', async () => {
    withStation()
    const job = useJobStore()
    job.profiles[0]!.pens![0]!.offset_source = 'vision'
    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.find('[data-test="pen-measure-0"]').text()).toContain('Remeasure')
    expect(wrapper.find('[data-test="pen-measure-1"]').text()).toContain('Measure')
  })

  it('does not apply a low-confidence measurement', async () => {
    withStation()
    measureSpy.mockResolvedValue({
      found: true,
      slot: 1,
      is_reference: false,
      tip_px: { x: 130, y: 100 },
      confidence: 0.1, // below the trust threshold
      reference_measured: true,
      offset_mm: { x: 1.8, y: -0.5 },
      message: 'ok',
      annotated_image: 'data:image/jpeg;base64,AAAA',
    })
    const wrapper = mountPanel()
    await flushPromises()
    saveSpy.mockClear()
    await wrapper.find('[data-test="pen-measure-1"]').trigger('click')
    await flushPromises()
    // Not written, but the frame + warning are shown.
    expect(saveSpy).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="pen-measure-msg-1"]').text()).toContain('Low confidence')
    expect(wrapper.find('[data-test="pen-measure-preview-1"]').exists()).toBe(true)
  })

  it('persists the dark threshold from the Advanced panel', async () => {
    withStation()
    const wrapper = mountPanel()
    await flushPromises()
    const input = wrapper.find('[data-test="tip-dark-threshold"]')
    await input.setValue('120')
    await input.trigger('change')
    await nextTick()
    expect((saveSpy.mock.calls.at(-1)![0] as MachineProfile).tip_calibration?.dark_threshold).toBe(
      120,
    )
  })

  it('persists the frames-to-average count and sends it when measuring', async () => {
    withStation()
    const wrapper = mountPanel()
    await flushPromises()
    const input = wrapper.find('[data-test="tip-samples"]')
    expect(input.exists()).toBe(true)
    await input.setValue('4')
    await input.trigger('change')
    await nextTick()
    expect((saveSpy.mock.calls.at(-1)![0] as MachineProfile).tip_calibration?.samples).toBe(4)
    await wrapper.find('[data-test="pen-measure-1"]').trigger('click')
    await flushPromises()
    expect(measureSpy).toHaveBeenCalledWith(expect.objectContaining({ samples: 4 }))
  })

  it('clamps the frames-to-average count to 1–20', async () => {
    withStation()
    const wrapper = mountPanel()
    await flushPromises()
    const input = wrapper.find('[data-test="tip-samples"]')
    await input.setValue('99')
    await input.trigger('change')
    await nextTick()
    expect((saveSpy.mock.calls.at(-1)![0] as MachineProfile).tip_calibration?.samples).toBe(20)
  })

  it('flags a suspiciously large offset but still applies it', async () => {
    withStation()
    measureSpy.mockResolvedValue({
      found: true,
      slot: 1,
      is_reference: false,
      tip_px: { x: 800, y: 100 },
      confidence: 0.9,
      reference_measured: true,
      offset_mm: { x: 70, y: 0 }, // 70 mm — beyond the sanity bound
      message: 'ok',
      annotated_image: 'data:image/jpeg;base64,AAAA',
    })
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('[data-test="pen-measure-1"]').trigger('click')
    await flushPromises()
    await nextTick()
    // Still written (it cleared the confidence gate)…
    const pen1 = (saveSpy.mock.calls.at(-1)![0] as MachineProfile).pens?.find((p) => p.index === 1)
    expect(pen1?.offset_source).toBe('vision')
    // …but the message carries the large-offset warning.
    expect(wrapper.find('[data-test="pen-measure-msg-1"]').text()).toContain('large offset')
  })

  it('shows the repeatability spread of an averaged measurement', async () => {
    withStation()
    measureSpy.mockResolvedValue({
      found: true,
      slot: 1,
      is_reference: false,
      tip_px: { x: 130, y: 100 },
      confidence: 0.9,
      spread_mm: 0.4, // tight agreement
      reference_measured: true,
      offset_mm: { x: 1, y: 0 },
      message: 'ok',
      annotated_image: null,
    })
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('[data-test="pen-measure-1"]').trigger('click')
    await flushPromises()
    await nextTick()
    expect(wrapper.find('[data-test="pen-measure-msg-1"]').text()).toContain('±0.40 mm')
  })

  it('warns and still applies when averaged frames disagree too much', async () => {
    withStation()
    measureSpy.mockResolvedValue({
      found: true,
      slot: 1,
      is_reference: false,
      tip_px: { x: 130, y: 100 },
      confidence: 0.9,
      spread_mm: 3.0, // beyond the stability bound
      reference_measured: true,
      offset_mm: { x: 1, y: 0 },
      message: 'ok',
      annotated_image: null,
    })
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('[data-test="pen-measure-1"]').trigger('click')
    await flushPromises()
    await nextTick()
    // Applied (confident per frame)…
    const pen1 = (saveSpy.mock.calls.at(-1)![0] as MachineProfile).pens?.find((p) => p.index === 1)
    expect(pen1?.offset_source).toBe('vision')
    // …but the instability warning shows.
    expect(wrapper.find('[data-test="pen-measure-msg-1"]').text()).toContain('frames vary by')
  })

  it('test detection shows a result without writing an offset', async () => {
    withStation()
    measureSpy.mockResolvedValue({
      found: true,
      slot: 0,
      is_reference: true,
      tip_px: { x: 100, y: 100 },
      confidence: 0.9,
      reference_measured: true,
      offset_mm: { x: 0, y: 0 },
      message: 'ok',
      annotated_image: 'data:image/jpeg;base64,AAAA',
    })
    const wrapper = mountPanel()
    await flushPromises()
    saveSpy.mockClear()
    await wrapper.find('[data-test="tip-test"]').trigger('click')
    await flushPromises()
    expect(measureSpy).toHaveBeenCalled()
    expect(saveSpy).not.toHaveBeenCalled() // dry run — nothing persisted
    expect(wrapper.find('[data-test="tip-test-preview"]').exists()).toBe(true)
  })

  it('clears a pen offset back to unset', async () => {
    withStation()
    const job = useJobStore()
    job.profiles[0]!.pens![1]!.offset_source = 'vision'
    job.profiles[0]!.pens![1]!.xy_offset_mm = { x: 2, y: 1 }
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('[data-test="pen-clear-1"]').trigger('click')
    await nextTick()
    const pen1 = (saveSpy.mock.calls.at(-1)![0] as MachineProfile).pens?.find((p) => p.index === 1)
    expect(pen1?.offset_source).toBe('unset')
    expect(pen1?.xy_offset_mm).toEqual({ x: 0, y: 0 })
  })

  it('hides Measure until a station is configured', async () => {
    const job = useJobStore()
    job.profiles[0]!.apply_pen_offsets = true
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.find('[data-test="pen-measure-1"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="use-tip-station"]').exists()).toBe(true)
  })

  it('measures a tip and applies the offset with vision provenance', async () => {
    withStation()
    measureSpy.mockResolvedValue({
      found: true,
      slot: 1,
      is_reference: false,
      tip_px: { x: 130, y: 100 },
      confidence: 0.9,
      reference_measured: true,
      offset_mm: { x: 1.8, y: -0.5 },
      message: 'ok',
      annotated_image: 'data:image/jpeg;base64,AAAA',
    })
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.find('[data-test="pen-measure-1"]').trigger('click')
    await flushPromises()
    await nextTick()

    expect(measureSpy).toHaveBeenCalledWith(
      expect.objectContaining({ slot: 1, camera_url: 'cam://x', reference_slot: 0 }),
    )
    const pen1 = (saveSpy.mock.calls.at(-1)![0] as MachineProfile).pens?.find((p) => p.index === 1)
    expect(pen1?.xy_offset_mm).toEqual({ x: 1.8, y: -0.5 })
    expect(pen1?.offset_source).toBe('vision')
    const preview = wrapper.find('[data-test="pen-measure-preview-1"]')
    expect(preview.attributes('src')).toBe('data:image/jpeg;base64,AAAA')
  })

  it('persists a detection-zone (ROI) and sends it when measuring', async () => {
    withStation()
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.find('[data-test="tip-roi-x"]').setValue('10')
    await wrapper.find('[data-test="tip-roi-x"]').trigger('change')
    await wrapper.find('[data-test="tip-roi-w"]').setValue('40')
    await wrapper.find('[data-test="tip-roi-w"]').trigger('change')
    await wrapper.find('[data-test="tip-roi-h"]').setValue('30')
    await wrapper.find('[data-test="tip-roi-h"]').trigger('change')
    await nextTick()
    expect((saveSpy.mock.calls.at(-1)![0] as MachineProfile).tip_calibration?.roi).toEqual({
      x: 10,
      y: 0,
      width: 40,
      height: 30,
    })
  })

  it('sends an optional station Z with the measurement', async () => {
    withStation({ station_position: { x: 20, y: 30 } })
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('[data-test="tip-station-z"]').setValue('4')
    await wrapper.find('[data-test="tip-station-z"]').trigger('change')
    await nextTick()
    await wrapper.find('[data-test="tip-auto-move"]').setValue(true)
    await wrapper.find('[data-test="pen-measure-1"]').trigger('click')
    await flushPromises()
    expect(measureSpy).toHaveBeenCalledWith(
      expect.objectContaining({ move_to_station: true, station_z_mm: 4 }),
    )
  })

  it('passes the light flag + GPIO pin when light-during-measure is on', async () => {
    withStation({ light_gpio_pin: 17, light_active_high: true })
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('[data-test="pen-measure-1"]').trigger('click')
    await flushPromises()
    expect(measureSpy).toHaveBeenCalledWith(
      expect.objectContaining({ light: true, light_gpio_pin: 17, light_active_high: true }),
    )
  })

  it('shows station readiness chips so setup blockers are visible', async () => {
    withStation({ camera_url: '', mm_per_pixel: 0, roi: null })
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.find('[data-test="tip-ready-camera"]').text()).toContain('⚠')
    expect(wrapper.find('[data-test="tip-ready-scale"]').text()).toContain('⚠')
    expect(wrapper.find('[data-test="tip-ready-reference"]').text()).toContain('✓')
    expect(wrapper.find('[data-test="tip-ready-zone"]').text()).toContain('·')
  })

  it('shows the next setup action and blocks camera measurement until ready', async () => {
    withStation({ camera_url: '' })
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.find('[data-test="offset-next-action"]').text()).toContain('Next camera')
    expect((wrapper.find('[data-test="guide-start"]').element as HTMLButtonElement).disabled).toBe(
      true,
    )
    expect((wrapper.find('[data-test="pen-measure-1"]').element as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it('marks the guided camera flow ready when required setup is complete', async () => {
    withStation()
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.find('[data-test="offset-next-action"]').text()).toContain('Ready to measure')
    expect((wrapper.find('[data-test="guide-start"]').element as HTMLButtonElement).disabled).toBe(
      false,
    )
  })

  it('defaults light-during-measure on when a GPIO light pin is configured', async () => {
    withStation({ light_gpio_pin: 17 })
    const wrapper = mountPanel()
    await flushPromises()
    expect((wrapper.find('[data-test="tip-light-during"]').element as HTMLInputElement).checked).toBe(
      true,
    )
  })

  it('manual light buttons drive the configured GPIO pin', async () => {
    withStation({ light_gpio_pin: 17, light_active_high: true })
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('[data-test="tip-light-on"]').trigger('click')
    await flushPromises()
    expect(lightSpy).toHaveBeenCalledWith(17, true, true)
    expect(wrapper.find('[data-test="tip-light-msg"]').text()).toBe('Light on')
    await wrapper.find('[data-test="tip-light-off"]').trigger('click')
    await flushPromises()
    expect(lightSpy).toHaveBeenCalledWith(17, false, true)
    expect(wrapper.find('[data-test="tip-light-msg"]').text()).toBe('Light off')
  })

  it('offers the GPIO pins from the backend in the pin dropdown', async () => {
    withStation()
    const wrapper = mountPanel()
    await flushPromises()
    const options = wrapper.find('[data-test="tip-light-pin"]').findAll('option')
    expect(options.map((o) => o.text())).toContain('GPIO 18')
  })

  it('can point the offset camera at a configured workshop camera', async () => {
    withStation()
    const ui = useUiStore()
    ui.cameras[0] = { enabled: true, url: 'http://cam-a/stream', label: 'Offset cam' }
    const wrapper = mountPanel()
    await flushPromises()
    const select = wrapper.find('[data-test="tip-camera-source"]')
    expect(select.exists()).toBe(true)
    await select.setValue('http://cam-a/stream')
    await nextTick()
    expect((saveSpy.mock.calls.at(-1)![0] as MachineProfile).tip_calibration?.camera_url).toBe(
      'http://cam-a/stream',
    )
  })

  it('runs the mm/pixel assistant and applies the derived scale', async () => {
    withStation()
    scaleSpy.mockResolvedValue({
      found: true,
      mm_per_pixel: 0.5,
      width_px: 40,
      height_px: 40,
      annotated_image: 'data:image/jpeg;base64,AAAA',
      message: 'ok',
    })
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('[data-test="tip-scale-known-mm"]').setValue(20)
    await wrapper.find('[data-test="tip-scale-measure"]').trigger('click')
    await flushPromises()
    expect(scaleSpy).toHaveBeenCalledWith(expect.objectContaining({ known_mm: 20 }))
    expect((saveSpy.mock.calls.at(-1)![0] as MachineProfile).tip_calibration?.mm_per_pixel).toBe(
      0.5,
    )
    expect(wrapper.find('[data-test="tip-scale-preview"]').exists()).toBe(true)
  })

  it('passes fetch_pen when the load-from-magazine toggle is on', async () => {
    withStation()
    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.find('[data-test="tip-fetch-pen"]').setValue(true)
    await wrapper.find('[data-test="pen-measure-1"]').trigger('click')
    await flushPromises()
    expect(measureSpy).toHaveBeenCalledWith(
      expect.objectContaining({ fetch_pen: true, profile_name: 'P' }),
    )
  })

  it('reports a failed detection without applying an offset', async () => {
    withStation()
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
    const wrapper = mountPanel()
    await flushPromises()
    saveSpy.mockClear()
    await wrapper.find('[data-test="pen-measure-1"]').trigger('click')
    await flushPromises()
    expect(saveSpy).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="pen-measure-msg-1"]').text()).toBeTruthy()
  })
})
