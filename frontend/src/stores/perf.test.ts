// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import PerfOverlay from '../components/v2/PerfOverlay.vue'
import { usePerfTracker } from '../composables/usePerfTracker'
import { usePerfStore } from './perf'
import { useUiModeStore } from './uiMode'

describe('usePerfStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
    window.history.replaceState({}, '', '/')
  })

  it('records timing samples and exposes a per-KPI summary', () => {
    const store = usePerfStore()
    store.recordTiming('preview_refresh', 80)
    store.recordTiming('preview_refresh', 120)
    store.recordTiming('preview_refresh', 200)
    const summary = store.summary('preview_refresh')
    expect(summary.count).toBe(3)
    expect(summary.p50).toBe(120)
    expect(summary.last).toBe(200)
  })

  it('counts network_error samples in `errors`', () => {
    const store = usePerfStore()
    store.record({ kpi: 'network_error', value: 1, recorded_at: Date.now() })
    store.record({ kpi: 'network_error', value: 1, recorded_at: Date.now() })
    expect(store.errors).toBe(2)
  })

  it('clear() drops all samples and resets error count', () => {
    const store = usePerfStore()
    store.recordTiming('preview_refresh', 30)
    store.record({ kpi: 'network_error', value: 1, recorded_at: Date.now() })
    store.clear()
    expect(store.samples).toEqual([])
    expect(store.errors).toBe(0)
  })

  it('caps samples to RING_SIZE', () => {
    const store = usePerfStore()
    for (let i = 0; i < 250; i++) store.recordTiming('preview_refresh', i)
    expect(store.samples.length).toBeLessThanOrEqual(200)
    // The oldest samples were evicted.
    const summary = store.summary('preview_refresh')
    expect(summary.p50).toBeGreaterThan(0)
  })

  it('summary returns zeros for an empty KPI', () => {
    const store = usePerfStore()
    expect(store.summary('frame_drop')).toEqual({ count: 0, p50: 0, p95: 0, last: 0 })
  })
})

describe('usePerfTracker', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('records a synchronous timing sample for time()', () => {
    const store = usePerfStore()
    const tracker = usePerfTracker()
    const result = tracker.time('preview_refresh', 'label', () => 42)
    expect(result).toBe(42)
    expect(store.summary('preview_refresh').count).toBe(1)
  })

  it('records an async timing sample for timeAsync()', async () => {
    const store = usePerfStore()
    const tracker = usePerfTracker()
    const result = await tracker.timeAsync('time_to_first_preview', 'preview', async () => {
      await new Promise((r) => setTimeout(r, 1))
      return 'ok'
    })
    expect(result).toBe('ok')
    expect(store.summary('time_to_first_preview').count).toBe(1)
  })

  it('still records when the wrapped fn throws', () => {
    const store = usePerfStore()
    const tracker = usePerfTracker()
    expect(() => tracker.time('preview_refresh', undefined, () => { throw new Error('boom') })).toThrow()
    expect(store.summary('preview_refresh').count).toBe(1)
  })

  it('recordError pushes a network_error sample', () => {
    const store = usePerfStore()
    const tracker = usePerfTracker()
    tracker.recordError('/upload')
    expect(store.errors).toBe(1)
  })
})

describe('PerfOverlay', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
    window.history.replaceState({}, '', '/')
  })

  it('is hidden by default (feature flag off)', () => {
    const wrapper = mount(PerfOverlay)
    expect(wrapper.find('[data-test="perf-overlay"]').exists()).toBe(false)
  })

  it('renders when the perf flag is on', () => {
    const ui = useUiModeStore()
    ui.setFlag('perf', true)
    const wrapper = mount(PerfOverlay)
    expect(wrapper.find('[data-test="perf-overlay"]').exists()).toBe(true)
  })

  it('renders the configured KPI rows once visible', () => {
    const ui = useUiModeStore()
    ui.setFlag('perf', true)
    const wrapper = mount(PerfOverlay)
    expect(wrapper.find('[data-test="perf-row-time_to_first_preview"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="perf-row-preview_refresh"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="perf-row-slow_interaction"]').exists()).toBe(true)
  })

  it('clear button empties the store', async () => {
    const ui = useUiModeStore()
    ui.setFlag('perf', true)
    const store = usePerfStore()
    store.recordTiming('preview_refresh', 100)
    const wrapper = mount(PerfOverlay)
    await wrapper.find('[data-test="perf-clear"]').trigger('click')
    expect(store.summary('preview_refresh').count).toBe(0)
  })
})
