// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { MAX_CAMERAS, useUiStore } from './ui'

describe('ui store — camera config', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('defaults to two blank, disabled camera slots', () => {
    const ui = useUiStore()
    expect(ui.cameras).toHaveLength(MAX_CAMERAS)
    expect(ui.cameras.every((c) => !c.enabled && c.url === '' && c.label === '')).toBe(true)
  })

  it('migrates the legacy single-camera config into slot 0', () => {
    localStorage.setItem('omniplot.cameraEnabled', '1')
    localStorage.setItem('omniplot.cameraUrl', 'http://old/stream')
    setActivePinia(createPinia()) // re-create so the store re-reads localStorage
    const ui = useUiStore()
    expect(ui.cameras[0]).toEqual({ enabled: true, url: 'http://old/stream', label: '' })
    expect(ui.cameras[1]!.enabled).toBe(false)
  })

  it('loads and normalizes the persisted list, padded to two slots', () => {
    localStorage.setItem(
      'omniplot.cameras',
      JSON.stringify([{ enabled: true, url: 'http://a', label: 'A', junk: 1 }]),
    )
    setActivePinia(createPinia())
    const ui = useUiStore()
    expect(ui.cameras).toHaveLength(MAX_CAMERAS)
    expect(ui.cameras[0]).toEqual({ enabled: true, url: 'http://a', label: 'A' })
    expect(ui.cameras[1]).toEqual({ enabled: false, url: '', label: '' })
  })

  it('persists camera edits to localStorage', async () => {
    const ui = useUiStore()
    ui.cameras[0]!.enabled = true
    ui.cameras[0]!.url = 'http://new/stream'
    await nextTick()
    const saved = JSON.parse(localStorage.getItem('omniplot.cameras') ?? '[]')
    expect(saved[0]).toMatchObject({ enabled: true, url: 'http://new/stream' })
  })
})
