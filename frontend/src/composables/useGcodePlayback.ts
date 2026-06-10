// Playback state machine for the Simulator (L10 #1 extract).
//
// Wraps the lifecycle that used to live inline at the top of
// ``Simulator.vue``:
//   - reparse G-code into a ``SimResult`` whenever the source or
//     profile changes
//   - drive ``simTime`` via a requestAnimationFrame loop while playing
//   - expose play / pause / restart / jumpToEnd / seek transitions
//
// Inputs are passed as refs so the composable stays decoupled from
// any specific store. The Simulator orchestrator wires
// ``useJobStore().gcode`` + the relevant profile fields in;
// future callers (e.g. unit tests, a standalone preview) can pass
// any reactive source.
//
// The composable owns its own RAF handle and registers an
// ``onBeforeUnmount`` cleanup so the caller doesn't have to remember.

import { onBeforeUnmount, ref, shallowRef, watch, type Ref } from 'vue'
import { parseGcode, type ParseOptions, type SimResult } from '../lib/gcode'

export interface PlaybackInputs {
  /** Source G-code text. ``null`` means "no plot yet" and parks the
   *  playback in an empty state (``sim.value`` stays ``null``). */
  gcode: Ref<string | null>
  /** Parse options derived from the active machine profile. ``null``
   *  while no profile is selected (``sim.value`` stays ``null`` then
   *  too, mirroring the original Simulator behaviour). */
  parseOptions: Ref<ParseOptions | null>
}

export interface PlaybackHandle {
  sim: Ref<SimResult | null>
  playing: Ref<boolean>
  simTime: Ref<number>
  speed: Ref<number>
  play: () => void
  pause: () => void
  restart: () => void
  jumpToEnd: () => void
  seek: (time: number) => void
  /** Re-runs ``parseGcode`` against the current inputs and resets
   *  ``simTime`` to the end of the plot. Called automatically when
   *  either input ref changes; exposed for callers that want to
   *  force a refresh without mutating inputs. */
  reparse: () => void
}

/**
 * Wire a reactive G-code source + parse-options pair into a
 * play / pause / seek state machine. Returns refs the caller can
 * bind into a renderer + controls UI.
 *
 * ``speed`` defaults to ``5×`` to match the Simulator toolbar's
 * preset row (1× / 5× / 100×); the original component opens at 5×.
 */
export function useGcodePlayback(inputs: PlaybackInputs): PlaybackHandle {
  // ``shallowRef`` on purpose: a parsed plot can hold tens of thousands
  // of ``SimSegment`` objects. A plain ``ref`` would wrap every segment
  // (and every field within) in a reactive Proxy — doubling memory and
  // routing each ``seg.x0`` read in the canvas hot loop through a getter.
  // The result is only ever replaced wholesale in ``reparse``, never
  // mutated field-by-field, so shallow reactivity (trigger on
  // reassignment only) is both correct and far cheaper.
  const sim = shallowRef<SimResult | null>(null)
  const playing = ref(false)
  const simTime = ref(0)
  const speed = ref(5)

  let raf = 0
  let last = 0

  function frame(now: number): void {
    const r = sim.value
    if (!playing.value || !r) return
    const dt = (now - last) / 1000
    last = now
    simTime.value = Math.min(r.totalTimeSeconds, simTime.value + dt * speed.value)
    if (simTime.value >= r.totalTimeSeconds) {
      playing.value = false
      return
    }
    raf = requestAnimationFrame(frame)
  }

  function play(): void {
    const r = sim.value
    if (!r) return
    // ``play`` after the plot finished should rewind to the start so
    // the operator doesn't have to hit Restart first — the toolbar's
    // big green button is one click, not two.
    if (simTime.value >= r.totalTimeSeconds) simTime.value = 0
    playing.value = true
    last = performance.now()
    raf = requestAnimationFrame(frame)
  }

  function pause(): void {
    playing.value = false
    cancelAnimationFrame(raf)
  }

  function restart(): void {
    pause()
    simTime.value = 0
  }

  function jumpToEnd(): void {
    const r = sim.value
    if (!r) return
    pause()
    simTime.value = r.totalTimeSeconds
  }

  function seek(time: number): void {
    const r = sim.value
    if (!r) return
    simTime.value = Math.max(0, Math.min(r.totalTimeSeconds, time))
  }

  function reparse(): void {
    pause()
    const code = inputs.gcode.value
    const opts = inputs.parseOptions.value
    if (!code || !opts) {
      sim.value = null
      simTime.value = 0
      return
    }
    sim.value = parseGcode(code, opts)
    // Default to the final frame so the operator sees the full result
    // the moment they open the tab. Press Restart / Play to scrub
    // back to the start of the plot.
    simTime.value = sim.value.totalTimeSeconds
  }

  // Auto-reparse whenever either input changes. ``immediate`` runs
  // the initial parse on hookup so callers don't have to remember to
  // call ``reparse()`` themselves after mount.
  watch(
    [inputs.gcode, inputs.parseOptions],
    () => {
      reparse()
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    cancelAnimationFrame(raf)
  })

  return {
    sim,
    playing,
    simTime,
    speed,
    play,
    pause,
    restart,
    jumpToEnd,
    seek,
    reparse,
  }
}
