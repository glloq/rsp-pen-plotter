// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import type { PrintRun } from '../api/client'
import WorkshopMode from '../components/v2/WorkshopMode.vue'
import fr from '../locales/fr.json'

const i18n = createI18n({ legacy: false, locale: 'fr', fallbackLocale: 'fr', messages: { fr } })
const globalConfig = { global: { plugins: [i18n] } }
import { useWorkspacesStore } from './workspaces'

describe('useWorkspacesStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
  })

  it('starts on the Beginner builtin and exposes both presets', () => {
    const store = useWorkspacesStore()
    expect(store.all.length).toBe(2)
    expect(store.active.id).toBe('builtin.beginner')
    expect(store.active.panels).toContain('source')
    expect(store.active.panels).toContain('plot')
  })

  it('switches to Pro and persists the choice', async () => {
    const store = useWorkspacesStore()
    store.setActive('builtin.pro')
    await nextTick()
    const raw = window.localStorage.getItem('omniplot.workspaces.v1')
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw!).activeId).toBe('builtin.pro')
  })

  it('rejects setActive on an unknown workspace id', () => {
    const store = useWorkspacesStore()
    store.setActive('not-real')
    expect(store.active.id).toBe('builtin.beginner')
  })

  it('saveAs creates a custom workspace and activates it', () => {
    const store = useWorkspacesStore()
    const w = store.saveAs('My layout', ['preview', 'queue', 'magazine'])
    expect(w.id.startsWith('custom.')).toBe(true)
    expect(store.activeId).toBe(w.id)
    expect(store.custom.length).toBe(1)
    expect(store.active.panels).toEqual(['preview', 'queue', 'magazine'])
  })

  it('saveAs trims and rejects empty names', () => {
    const store = useWorkspacesStore()
    expect(() => store.saveAs('   ', ['preview'])).toThrow()
    expect(store.custom.length).toBe(0)
  })

  it('rename updates a custom workspace label only', () => {
    const store = useWorkspacesStore()
    const w = store.saveAs('Original', ['preview'])
    store.rename(w.id, 'Renamed')
    expect(store.custom[0]?.name).toBe('Renamed')
    // Builtin not renameable.
    store.rename('builtin.beginner', 'Hacked')
    expect(store.all[0]?.name).toBe('Débutant')
  })

  it('remove drops a custom workspace and resets active', () => {
    const store = useWorkspacesStore()
    const w = store.saveAs('Tmp', ['preview'])
    expect(store.activeId).toBe(w.id)
    expect(store.remove(w.id)).toBe(true)
    expect(store.activeId).toBe('builtin.beginner')
    expect(store.custom.length).toBe(0)
  })

  it('remove returns false on unknown id', () => {
    const store = useWorkspacesStore()
    expect(store.remove('nope')).toBe(false)
  })

  it('restores persisted custom workspaces on next init', () => {
    window.localStorage.setItem(
      'omniplot.workspaces.v1',
      JSON.stringify({
        activeId: 'custom.x.y',
        custom: [{ id: 'custom.x.y', name: 'Saved', panels: ['preview'] }],
      }),
    )
    setActivePinia(createPinia())
    const store = useWorkspacesStore()
    expect(store.activeId).toBe('custom.x.y')
    expect(store.custom[0]?.name).toBe('Saved')
  })

  it('tolerates a corrupted persisted payload', () => {
    window.localStorage.setItem('omniplot.workspaces.v1', '{not-json')
    setActivePinia(createPinia())
    const store = useWorkspacesStore()
    expect(store.active.id).toBe('builtin.beginner')
  })
})

function makeRun(over: Partial<PrintRun> = {}): PrintRun {
  return {
    id: 'r1',
    name: 'Job',
    profile_name: 'AxiDraw V3',
    gcode: '',
    total_lines: 1000,
    acked_lines: 250,
    state: 'running',
    priority: 0,
    error: null,
    created_at: '2026-05-27T22:00:00Z',
    updated_at: '2026-05-27T22:01:00Z',
    ...over,
  }
}

describe('WorkshopMode', () => {
  it('shows the running run with progress', () => {
    const wrapper = mount(WorkshopMode, {
      ...globalConfig,
      props: { run: makeRun() },
    })
    expect(wrapper.find('[data-test="workshop-run-r1"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('25 %')
  })

  it('renders empty state when run is null', () => {
    const wrapper = mount(WorkshopMode, { ...globalConfig, props: { run: null } })
    expect(wrapper.find('[data-test="workshop-empty"]').exists()).toBe(true)
  })

  it('shows the hint and Resume button when paused', () => {
    const wrapper = mount(WorkshopMode, {
      ...globalConfig,
      props: {
        run: makeRun({ state: 'paused' }),
        nextActionHint: 'Insérer pen Cyan.',
      },
    })
    expect(wrapper.find('[data-test="workshop-hint"]').text()).toContain('Cyan')
    expect(wrapper.find('[data-test="workshop-resume"]').exists()).toBe(true)
  })

  it('only shows Pause button when running', () => {
    const wrapper = mount(WorkshopMode, {
      ...globalConfig,
      props: { run: makeRun({ state: 'running' }) },
    })
    expect(wrapper.find('[data-test="workshop-pause"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="workshop-resume"]').exists()).toBe(false)
  })

  it('emits exit on the close button', async () => {
    const wrapper = mount(WorkshopMode, { ...globalConfig, props: { run: makeRun() } })
    await wrapper.find('[data-test="workshop-exit"]').trigger('click')
    expect(wrapper.emitted('exit')).toBeTruthy()
  })

  it('emits pause/resume from the buttons', async () => {
    const wrapper = mount(WorkshopMode, {
      ...globalConfig,
      props: { run: makeRun({ state: 'running' }) },
    })
    await wrapper.find('[data-test="workshop-pause"]').trigger('click')
    expect(wrapper.emitted('pause')).toBeTruthy()
    await wrapper.setProps({ run: makeRun({ state: 'paused' }) })
    await wrapper.find('[data-test="workshop-resume"]').trigger('click')
    expect(wrapper.emitted('resume')).toBeTruthy()
  })
})
