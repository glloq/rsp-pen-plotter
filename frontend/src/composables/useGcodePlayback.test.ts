// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, ref, type Ref } from 'vue'
import { useGcodePlayback, type PlaybackHandle } from './useGcodePlayback'
import type { ParseOptions } from '../lib/gcode'

// The composable owns a requestAnimationFrame loop and registers an
// ``onBeforeUnmount`` cleanup. To exercise it under vitest we mount a
// tiny host component that calls it once and exposes the handle, so
// the lifecycle hooks fire correctly and the test can drive the
// composable from the outside.

const SAMPLE_GCODE = `G21
G90
G0 X0 Y0
M3 S1000
G1 X10 Y10 F1800
M3 S0
G0 X0 Y0
`

const PARSE_OPTIONS: ParseOptions = {
  penUpCommand: 'M3 S0',
  penDownCommand: 'M3 S1000',
  travelSpeedMmS: 80,
  defaultDrawSpeedMmS: 30,
  toolChangeCommand: 'M0',
}

function mountHost(gcode: Ref<string | null>, opts: Ref<ParseOptions | null>) {
  let handle: PlaybackHandle | undefined
  const Host = defineComponent({
    setup() {
      handle = useGcodePlayback({ gcode, parseOptions: opts })
      return () => null
    },
  })
  const wrapper = mount(Host)
  if (!handle) throw new Error('handle was not captured')
  return { wrapper, handle }
}

describe('useGcodePlayback', () => {
  beforeEach(() => {
    // happy-dom's RAF schedules on a real timer; stubbing keeps the
    // RAF loop deterministic across cases.
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('parses on mount when both inputs are present', () => {
    // The composable runs ``reparse`` immediately on hookup so the
    // caller doesn't have to remember to bootstrap.
    const gcode = ref<string | null>(SAMPLE_GCODE)
    const opts = ref<ParseOptions | null>(PARSE_OPTIONS)
    const { handle } = mountHost(gcode, opts)
    expect(handle.sim.value).not.toBeNull()
    expect(handle.sim.value!.segments.length).toBeGreaterThan(0)
    // ``simTime`` defaults to the end so the operator sees the
    // finished plot, not an empty canvas.
    expect(handle.simTime.value).toBe(handle.sim.value!.totalTimeSeconds)
  })

  it('stays parked when gcode is null', () => {
    const gcode = ref<string | null>(null)
    const opts = ref<ParseOptions | null>(PARSE_OPTIONS)
    const { handle } = mountHost(gcode, opts)
    expect(handle.sim.value).toBeNull()
    expect(handle.simTime.value).toBe(0)
  })

  it('stays parked when parseOptions is null', () => {
    const gcode = ref<string | null>(SAMPLE_GCODE)
    const opts = ref<ParseOptions | null>(null)
    const { handle } = mountHost(gcode, opts)
    expect(handle.sim.value).toBeNull()
  })

  it('reparses when gcode changes', async () => {
    const gcode = ref<string | null>(SAMPLE_GCODE)
    const opts = ref<ParseOptions | null>(PARSE_OPTIONS)
    const { handle, wrapper } = mountHost(gcode, opts)
    const firstSim = handle.sim.value
    expect(firstSim).not.toBeNull()
    gcode.value = `G21\nG90\nG0 X0 Y0\nM3 S1000\nG1 X20 Y20 F1800\n`
    await wrapper.vm.$nextTick()
    expect(handle.sim.value).not.toBe(firstSim)
    expect(handle.sim.value!.bounds.maxX).toBeGreaterThan(firstSim!.bounds.maxX)
  })

  it('play flips playing=true and rewinds when called at the end', () => {
    const gcode = ref<string | null>(SAMPLE_GCODE)
    const opts = ref<ParseOptions | null>(PARSE_OPTIONS)
    const { handle } = mountHost(gcode, opts)
    // After mount the playback parks at the end of the plot.
    const totalTime = handle.sim.value!.totalTimeSeconds
    expect(handle.simTime.value).toBe(totalTime)
    handle.play()
    expect(handle.playing.value).toBe(true)
    // ``play`` from the end rewinds to 0 so a single click on the
    // toolbar starts a fresh playback instead of staying parked.
    expect(handle.simTime.value).toBe(0)
    handle.pause()
  })

  it('pause flips playing=false and cancels the RAF loop', () => {
    const gcode = ref<string | null>(SAMPLE_GCODE)
    const opts = ref<ParseOptions | null>(PARSE_OPTIONS)
    const { handle } = mountHost(gcode, opts)
    handle.play()
    expect(handle.playing.value).toBe(true)
    handle.pause()
    expect(handle.playing.value).toBe(false)
  })

  it('restart pauses and rewinds simTime to 0', () => {
    const gcode = ref<string | null>(SAMPLE_GCODE)
    const opts = ref<ParseOptions | null>(PARSE_OPTIONS)
    const { handle } = mountHost(gcode, opts)
    handle.play()
    handle.restart()
    expect(handle.playing.value).toBe(false)
    expect(handle.simTime.value).toBe(0)
  })

  it('jumpToEnd pauses and parks at totalTimeSeconds', () => {
    const gcode = ref<string | null>(SAMPLE_GCODE)
    const opts = ref<ParseOptions | null>(PARSE_OPTIONS)
    const { handle } = mountHost(gcode, opts)
    handle.restart()
    expect(handle.simTime.value).toBe(0)
    handle.jumpToEnd()
    expect(handle.playing.value).toBe(false)
    expect(handle.simTime.value).toBe(handle.sim.value!.totalTimeSeconds)
  })

  it('seek clamps the requested time into [0, totalTimeSeconds]', () => {
    const gcode = ref<string | null>(SAMPLE_GCODE)
    const opts = ref<ParseOptions | null>(PARSE_OPTIONS)
    const { handle } = mountHost(gcode, opts)
    const total = handle.sim.value!.totalTimeSeconds
    handle.seek(total / 2)
    expect(handle.simTime.value).toBeCloseTo(total / 2)
    handle.seek(-100)
    expect(handle.simTime.value).toBe(0)
    handle.seek(total * 10)
    expect(handle.simTime.value).toBe(total)
  })

  it('seek is a no-op when no plot is loaded', () => {
    const gcode = ref<string | null>(null)
    const opts = ref<ParseOptions | null>(PARSE_OPTIONS)
    const { handle } = mountHost(gcode, opts)
    handle.seek(5)
    expect(handle.simTime.value).toBe(0)
  })

  it('cleans up the RAF loop on unmount', () => {
    const cancel = vi.spyOn(globalThis, 'cancelAnimationFrame')
    const gcode = ref<string | null>(SAMPLE_GCODE)
    const opts = ref<ParseOptions | null>(PARSE_OPTIONS)
    const { wrapper, handle } = mountHost(gcode, opts)
    handle.play()
    wrapper.unmount()
    // The composable registers ``onBeforeUnmount`` so the host's
    // teardown nukes any pending RAF — otherwise a future tick would
    // try to mutate a disposed ref.
    expect(cancel).toHaveBeenCalled()
  })
})
