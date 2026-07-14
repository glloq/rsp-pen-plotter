// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TipDetectionTuner from './TipDetectionTuner.vue'
import type { TipCalibrationConfig } from '../api/client'

const measureSpy = vi.hoisted(() => vi.fn())

vi.mock('../api/client', async (importActual) => {
  const actual = await importActual<typeof import('../api/client')>()
  return { ...actual, measureTipOffset: measureSpy }
})

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      offsetCamera: {
        title: 'Offset camera',
        tuneTitle: 'Detection tuning',
        tuneHint: 'tune it',
        tipStyle: 'Tip type',
        tipStyleDark: 'Dark tip',
        tipStyleLight: 'Light tip',
        tipStyleHint: 'match the background',
        samples: 'Frames to average',
        testDetection: 'Test detection',
        testResult: 'Detected {c}%',
        autoTest: 'Auto re-test',
        confidence: 'Detection confidence',
        repeatability: '(±{mm} mm)',
        unstable: '⚠ frames vary by {mm} mm',
      },
      magazine: {
        darkThreshold: 'Detection threshold',
        measuring: 'Measuring…',
        measureNotFound: 'No tip detected',
        measureFailed: 'Measurement failed',
      },
      cameraPreview: { empty: 'no url', retry: 'retry', refresh: 'refresh', dragHint: 'drag' },
      camera: { streamError: 'stream error', live: 'live', title: 'camera' },
    },
  },
})

function makeConfig(extra: Partial<TipCalibrationConfig> = {}): TipCalibrationConfig {
  return {
    camera_url: 'cam://x',
    station_position: null,
    reference_slot: 0,
    mm_per_pixel: 0.1,
    detector: 'dark_blob',
    tip_style: 'dark',
    dark_threshold: 80,
    samples: 1,
    roi: null,
    ...extra,
  }
}

function found(confidence = 0.9, spread: number | null = null) {
  return {
    found: true,
    slot: 0,
    is_reference: true,
    tip_px: { x: 100, y: 100 },
    confidence,
    spread_mm: spread,
    reference_measured: true,
    offset_mm: { x: 0, y: 0 },
    message: 'ok',
    annotated_image: 'data:image/jpeg;base64,AAAA',
  }
}

function mountTuner(config = makeConfig()) {
  return mount(TipDetectionTuner, {
    props: { config },
    global: { plugins: [i18n] },
  })
}

describe('TipDetectionTuner', () => {
  beforeEach(() => {
    measureSpy.mockReset()
    measureSpy.mockResolvedValue(found())
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('emits a tip-style patch when the select changes', async () => {
    const wrapper = mountTuner()
    const select = wrapper.find('[data-test="tip-style"]')
    expect((select.element as HTMLSelectElement).value).toBe('dark')
    await select.setValue('light') // setValue fires the change event itself
    expect(wrapper.emitted('update:config')).toEqual([[{ tip_style: 'light' }]])
  })

  it('slider drags render live but only commit the threshold on release', async () => {
    const wrapper = mountTuner()
    const slider = wrapper.find('[data-test="tip-threshold-slider"]')
    // A drag is a stream of input events without change: set the value and
    // fire input only (setValue would also fire change, i.e. the release).
    ;(slider.element as HTMLInputElement).value = '120'
    await slider.trigger('input')
    // Live label follows the drag…
    expect(wrapper.text()).toContain('120')
    // …but nothing was persisted yet.
    expect(wrapper.emitted('update:config')).toBeUndefined()
    await slider.trigger('change') // release commits
    expect(wrapper.emitted('update:config')).toEqual([[{ dark_threshold: 120 }]])
  })

  it('the threshold number field commits a clamped value', async () => {
    const wrapper = mountTuner()
    const input = wrapper.find('[data-test="tip-dark-threshold"]')
    await input.setValue('999')
    expect(wrapper.emitted('update:config')).toEqual([[{ dark_threshold: 255 }]])
  })

  it('emits a clamped samples patch', async () => {
    const wrapper = mountTuner()
    const input = wrapper.find('[data-test="tip-samples"]')
    await input.setValue('99')
    expect(wrapper.emitted('update:config')).toEqual([[{ samples: 20 }]])
  })

  it('emits an ROI patch when a zone is drawn on the preview', async () => {
    const wrapper = mountTuner()
    wrapper.findComponent({ name: 'CameraPreview' }).vm.$emit('update:roi', {
      x: 10,
      y: 20,
      width: 30,
      height: 40,
    })
    expect(wrapper.emitted('update:config')).toEqual([
      [{ roi: { x: 10, y: 20, width: 30, height: 40 } }],
    ])
  })

  it('runs a dry-run test and shows the confidence meter, message and frame', async () => {
    const wrapper = mountTuner()
    await wrapper.find('[data-test="tip-test"]').trigger('click')
    await flushPromises()
    // Dry run with the current tuning — never stored server-side.
    expect(measureSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        dry_run: true,
        tip_style: 'dark',
        dark_threshold: 80,
        camera_url: 'cam://x',
      }),
    )
    const bar = wrapper.find('[data-test="tip-confidence-bar"]')
    expect(bar.attributes('style')).toContain('width: 90%')
    expect(bar.classes()).toContain('bg-emerald-500')
    expect(wrapper.find('[data-test="tip-confidence-value"]').text()).toBe('90 %')
    expect(wrapper.find('[data-test="tip-test-msg"]').text()).toContain('Detected 90%')
    expect(wrapper.find('[data-test="tip-test-preview"]').exists()).toBe(true)
    // The trust gate is marked on the meter at 35%.
    expect(wrapper.find('[data-test="tip-confidence-gate"]').attributes('style')).toContain('35%')
  })

  it('shows an amber meter below the trust gate', async () => {
    measureSpy.mockResolvedValue(found(0.2))
    const wrapper = mountTuner()
    await wrapper.find('[data-test="tip-test"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="tip-confidence-bar"]').classes()).toContain('bg-amber-500')
  })

  it('reports a miss with an empty meter', async () => {
    measureSpy.mockResolvedValue({ ...found(), found: false, confidence: 0, message: '' })
    const wrapper = mountTuner()
    await wrapper.find('[data-test="tip-test"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="tip-test-msg"]').text()).toContain('No tip detected')
    expect(wrapper.find('[data-test="tip-confidence-bar"]').attributes('style')).toContain(
      'width: 0%',
    )
  })

  it('flags unstable averaged frames in the result message', async () => {
    measureSpy.mockResolvedValue(found(0.9, 3.0))
    const wrapper = mountTuner()
    await wrapper.find('[data-test="tip-test"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="tip-test-msg"]').text()).toContain('frames vary by')
  })

  it('auto re-test runs immediately on enable, then debounced after changes', async () => {
    vi.useFakeTimers()
    const wrapper = mountTuner()
    await wrapper.find('[data-test="tip-auto-test"]').setValue(true)
    expect(measureSpy).toHaveBeenCalledTimes(1) // immediate baseline run
    await vi.runAllTimersAsync()

    // A committed tuning change (the parent saved and passed a new config)
    // re-runs the dry-run after the debounce window.
    await wrapper.setProps({ config: makeConfig({ dark_threshold: 120 }) })
    expect(measureSpy).toHaveBeenCalledTimes(1) // not yet — debounced
    await vi.advanceTimersByTimeAsync(700)
    expect(measureSpy).toHaveBeenCalledTimes(2)
    expect(measureSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({ dark_threshold: 120, dry_run: true }),
    )
  })

  it('does not auto re-test when the toggle is off', async () => {
    vi.useFakeTimers()
    const wrapper = mountTuner()
    await wrapper.setProps({ config: makeConfig({ dark_threshold: 120 }) })
    await vi.advanceTimersByTimeAsync(1000)
    expect(measureSpy).not.toHaveBeenCalled()
  })

  it('disables the test button without a camera URL', () => {
    const wrapper = mountTuner(makeConfig({ camera_url: '' }))
    expect((wrapper.find('[data-test="tip-test"]').element as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it('surfaces a camera failure as an error message', async () => {
    measureSpy.mockRejectedValue({ response: { data: { message: 'Camera read failed: offline' } } })
    const wrapper = mountTuner()
    await wrapper.find('[data-test="tip-test"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="tip-test-msg"]').text()).toContain('Camera read failed')
    expect(wrapper.find('[data-test="tip-confidence-meter"]').exists()).toBe(false)
  })
})
