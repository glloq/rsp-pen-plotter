// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { useUiModeStore } from './uiMode'

describe('useUiModeStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
    // Reset URL so URL-flag tests don't bleed across.
    window.history.replaceState({}, '', '/')
  })

  it('defaults to assisted mode on first load', () => {
    const store = useUiModeStore()
    expect(store.mode).toBe('assisted')
    expect(store.isAssisted).toBe(true)
    expect(store.isExpert).toBe(false)
  })

  it('toggleMode flips between assisted and expert', () => {
    const store = useUiModeStore()
    store.toggleMode()
    expect(store.mode).toBe('expert')
    store.toggleMode()
    expect(store.mode).toBe('assisted')
  })

  it('persists mode to localStorage', async () => {
    const store = useUiModeStore()
    store.setMode('expert')
    await nextTick()
    const raw = window.localStorage.getItem('omniplot.uiMode.v1')
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw!).mode).toBe('expert')
  })

  it('restores persisted mode on init', () => {
    window.localStorage.setItem(
      'omniplot.uiMode.v1',
      JSON.stringify({ mode: 'expert', expertDisclosureLevel: 2, flags: {} }),
    )
    setActivePinia(createPinia())
    const store = useUiModeStore()
    expect(store.mode).toBe('expert')
    expect(store.expertDisclosureLevel).toBe(2)
  })

  it('setFlag persists feature flags', async () => {
    const store = useUiModeStore()
    store.setFlag('compareMode', true)
    await nextTick()
    expect(store.isFlagEnabled('compareMode')).toBe(true)
    const raw = window.localStorage.getItem('omniplot.uiMode.v1')
    expect(JSON.parse(raw!).flags).toEqual({ compareMode: true })
  })

  it('URL flag overrides persisted value', () => {
    window.localStorage.setItem(
      'omniplot.uiMode.v1',
      JSON.stringify({ mode: 'assisted', expertDisclosureLevel: 1, flags: { compareMode: false } }),
    )
    window.history.replaceState({}, '', '/?flag.compareMode=1')
    setActivePinia(createPinia())
    const store = useUiModeStore()
    expect(store.isFlagEnabled('compareMode')).toBe(true)
  })

  it('unknown flags default to false', () => {
    const store = useUiModeStore()
    expect(store.isFlagEnabled('mystery')).toBe(false)
  })

  it('tolerates corrupted localStorage payload', () => {
    window.localStorage.setItem('omniplot.uiMode.v1', '{not-json')
    setActivePinia(createPinia())
    const store = useUiModeStore()
    expect(store.mode).toBe('assisted')
    expect(store.isFlagEnabled('any')).toBe(false)
  })

  it('expert disclosure level only accepts 1 or 2', () => {
    const store = useUiModeStore()
    store.setExpertDisclosureLevel(2)
    expect(store.expertDisclosureLevel).toBe(2)
    store.setExpertDisclosureLevel(1)
    expect(store.expertDisclosureLevel).toBe(1)
  })
})
