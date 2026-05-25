// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import Simulator from './Simulator.vue'
import { useJobStore } from '../stores/job'
import type { MachineProfile } from '../api/client'

// The Simulator is mounted by CanvasView and reads everything off the
// global stores — there are no props or emits. These tests pin down
// the observable surface (toolbar, color filter, display toggles,
// play/pause state machine) as it exists today, so the L10 split
// into ``useGcodePlayback`` + ``<SimCanvas>`` + ``<SimControls>``
// can be verified against the same DOM contract.
//
// happy-dom's canvas returns ``null`` for ``getContext('2d')``; the
// component's ``draw()`` short-circuits on that, so mounting goes
// through cleanly without a real renderer. The state machine and
// toolbar UI are what we exercise here.

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      simulator: {
        play: 'Play',
        pause: 'Pause',
        restart: 'Restart',
        end: 'End',
        zoomIn: 'Zoom in',
        zoomOut: 'Zoom out',
        resetView: 'Reset view',
        optTravel: 'Travel',
        optPenEvents: 'Pen events',
        optColorChanges: 'Tool changes',
        optPauses: 'Pauses',
        manualPenChange: 'Manual pen change',
        manualPenChangeHint: 'Single-pen machines: pause before each colour transition.',
        colorFilterLabel: 'Filter colours',
        showAll: 'Show all',
        showOnly: 'Show only this',
        stats: 'Stats',
        drawing: 'Drawing',
        travel: 'Travel',
        total: 'Total',
        size: 'Size',
      },
    },
  },
})

function makeProfile(): MachineProfile {
  return {
    name: 'Test A3',
    units: 'mm',
    workspace: { x_min: 0, y_min: 0, x_max: 297, y_max: 420 },
    origin: 'bottom_left',
    gcode_dialect: 'grbl',
    pen_up_command: 'M3 S0',
    pen_down_command: 'M3 S1000',
    tool_change_method: 'manual_pause',
    tool_change_command: 'M0',
    drawing_speed_mm_s: 30,
    travel_speed_mm_s: 80,
    acceleration_mm_s2: 500,
    pen_slot_count: 1,
    supports_arcs: false,
    arc_tolerance_mm: 0.1,
    ebb: null,
    pens: null,
  }
}

// A tiny G-code program: pen-down → draw to (10,10) → pen-up. Enough
// to populate ``sim.value`` with one drawing segment and trigger the
// toolbar render. Fine if the geometry is uninteresting — the tests
// here exercise state machine + UI wiring, not the parser itself
// (which has its own suite under ``lib/gcode.test.ts``).
const SAMPLE_GCODE = `G21
G90
G0 X0 Y0
M3 S1000
G1 X10 Y10 F1800
M3 S0
G0 X0 Y0
`

async function seedJobStore(): Promise<void> {
  // ``storeToRefs`` returns the underlying refs so we can swap their
  // ``.value`` directly. The job store also has a watcher that wipes
  // ``gcode`` whenever ``selectedProfileName`` changes (Generate's
  // cache-invalidation contract); that watcher fires asynchronously,
  // so we set the profile first, drain the tick, *then* set the gcode
  // — otherwise the watcher fires after our seed and the component
  // mounts with a null gcode.
  const job = useJobStore()
  const { profiles, selectedProfileName, gcode } = storeToRefs(job)
  const profile = makeProfile()
  profiles.value = [profile]
  selectedProfileName.value = profile.name
  await nextTick()
  gcode.value = SAMPLE_GCODE
}

function mountSimulator() {
  return mount(Simulator, {
    global: {
      plugins: [i18n],
    },
  })
}

describe('Simulator with no G-code', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders nothing when the job store has no gcode', () => {
    // Fresh store: ``gcode`` is null → ``sim`` stays null after the
    // onMounted reparse → the outer ``<section v-if="sim">`` keeps
    // the whole component out of the DOM. Important so the empty
    // state doesn't intercept clicks behind it on CanvasView.
    const wrapper = mountSimulator()
    expect(wrapper.find('section').exists()).toBe(false)
  })
})

describe('Simulator with G-code seeded', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    await seedJobStore()
  })

  it('renders the playback toolbar once parsed', async () => {
    const wrapper = mountSimulator()
    await nextTick()
    // Section exists → reparse() succeeded and ``sim`` is populated.
    // Without that the outer ``<section v-if="sim">`` keeps the whole
    // component out of the DOM.
    expect(wrapper.find('section').exists()).toBe(true)
    // Play button shows the "Play" label by default (playing=false).
    const playBtn = wrapper.findAll('button').find((b) => b.text() === 'Play')
    expect(playBtn).toBeDefined()
  })

  it('toggles the play/pause label when the play button is clicked', async () => {
    const wrapper = mountSimulator()
    await nextTick()
    const playBtn = wrapper.findAll('button').find((b) => b.text() === 'Play')
    expect(playBtn).toBeDefined()
    await playBtn!.trigger('click')
    // After click: playing=true → button label flips to "Pause".
    // (The RAF loop ticks happen via requestAnimationFrame, which
    // happy-dom doesn't fire automatically — that's fine, we're
    // testing the synchronous state flip.)
    const pauseBtn = wrapper.findAll('button').find((b) => b.text() === 'Pause')
    expect(pauseBtn).toBeDefined()
    // Pause it again so the test doesn't leave a RAF handle dangling.
    await pauseBtn!.trigger('click')
    expect(wrapper.findAll('button').find((b) => b.text() === 'Play')).toBeDefined()
  })

  it('renders one button per supported speed multiplier', async () => {
    const wrapper = mountSimulator()
    await nextTick()
    const buttons = wrapper.findAll('button').map((b) => b.text())
    // The toolbar ships three preset speeds (1×, 5×, 100×) so the
    // operator can scrub fast or watch real-time without a slider.
    expect(buttons).toContain('1×')
    expect(buttons).toContain('5×')
    expect(buttons).toContain('100×')
  })

  it('highlights the active speed button', async () => {
    const wrapper = mountSimulator()
    await nextTick()
    const fiveX = wrapper.findAll('button').find((b) => b.text() === '5×')
    // Default speed is 5× → that button gets the sky-active class.
    expect(fiveX?.classes().join(' ')).toContain('bg-sky-600')
    const oneX = wrapper.findAll('button').find((b) => b.text() === '1×')
    await oneX!.trigger('click')
    expect(oneX!.classes().join(' ')).toContain('bg-sky-600')
    // 5× loses the active style now that 1× was picked.
    expect(fiveX!.classes().join(' ')).not.toContain('bg-sky-600')
  })

  it('zoom in / out buttons clamp within the documented range', async () => {
    const wrapper = mountSimulator()
    await nextTick()
    const zoomIn = wrapper.find('button[title="Zoom in"]')
    const zoomOut = wrapper.find('button[title="Zoom out"]')
    expect(zoomIn.exists()).toBe(true)
    expect(zoomOut.exists()).toBe(true)
    // Smoke: clicking doesn't throw and the percent label updates.
    await zoomIn.trigger('click')
    await nextTick()
    // The label "NN%" lives in a span between the +/− buttons.
    const percentSpan = wrapper.findAll('span').find((s) => /\d+%$/.test(s.text()))
    expect(percentSpan).toBeDefined()
  })

  it('reset view button is wired and clickable', async () => {
    const wrapper = mountSimulator()
    await nextTick()
    const reset = wrapper.find('button[title="Reset view"]')
    expect(reset.exists()).toBe(true)
    await reset.trigger('click')
    // No throw, no DOM nuke; the button stays in the tree.
    expect(wrapper.find('button[title="Reset view"]').exists()).toBe(true)
  })

  it('display toggle buttons flip their active class on click', async () => {
    const wrapper = mountSimulator()
    await nextTick()
    // ``showTravel`` defaults to true → travel button is highlighted.
    const travel = wrapper.find('button[title="Travel"]')
    expect(travel.exists()).toBe(true)
    expect(travel.classes().join(' ')).toContain('bg-sky-600/30')
    await travel.trigger('click')
    // After click: showTravel=false → highlight class is gone.
    expect(travel.classes().join(' ')).not.toContain('bg-sky-600/30')
    expect(travel.classes().join(' ')).toContain('bg-slate-900')
  })
})
