// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createI18n } from 'vue-i18n'
import type { PrintRun, RunState } from '../../api/client'
import fr from '../../locales/fr.json'
import RunActionsPanel from './RunActionsPanel.vue'
import RunTimeline from './RunTimeline.vue'

const i18n = createI18n({ legacy: false, locale: 'fr', fallbackLocale: 'fr', messages: { fr } })
const globalConfig = { global: { plugins: [i18n] } }

function makeRun(over: Partial<PrintRun> = {}): PrintRun {
  return {
    id: 'run-1',
    name: 'Test run',
    profile_name: 'Custom CoreXY A3',
    gcode: '',
    total_lines: 1000,
    acked_lines: 250,
    state: 'running' as RunState,
    priority: 0,
    error: null,
    created_at: '2026-05-27T22:00:00Z',
    updated_at: '2026-05-27T22:01:00Z',
    ...over,
  }
}

describe('RunTimeline', () => {
  it('marks the running phase as active and queued as done', () => {
    const wrapper = mount(RunTimeline, {
      ...globalConfig,
      props: { run: makeRun({ state: 'running' }) },
    })
    expect(wrapper.find('[data-test="phase-queued"]').classes()).toContain('done')
    expect(wrapper.find('[data-test="phase-running"]').classes()).toContain('active')
    expect(wrapper.find('[data-test="phase-paused"]').classes()).toContain('future')
  })

  it('renders failure badge for failed runs', () => {
    const wrapper = mount(RunTimeline, {
      ...globalConfig,
      props: { run: makeRun({ state: 'failed', error: 'transport lost' }) },
    })
    expect(wrapper.find('[data-test="run-badge-failed"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="run-error"]').text()).toContain('transport lost')
  })

  it('renders cancel badge for canceled runs', () => {
    const wrapper = mount(RunTimeline, {
      ...globalConfig,
      props: { run: makeRun({ state: 'canceled' }) },
    })
    expect(wrapper.find('[data-test="run-badge-canceled"]').exists()).toBe(true)
  })

  it('shows the line progress percentage', () => {
    const wrapper = mount(RunTimeline, {
      ...globalConfig,
      props: { run: makeRun({ acked_lines: 500, total_lines: 1000 }) },
    })
    expect(wrapper.find('[data-test="run-progress"]').text()).toContain('50 %')
  })

  it('handles total_lines=0 without dividing by zero', () => {
    const wrapper = mount(RunTimeline, {
      ...globalConfig,
      props: { run: makeRun({ acked_lines: 0, total_lines: 0 }) },
    })
    expect(wrapper.find('[data-test="run-progress"]').text()).toContain('0 %')
  })

  it('marks completed phase as active when the run is done', () => {
    const wrapper = mount(RunTimeline, {
      ...globalConfig,
      props: { run: makeRun({ state: 'completed' }) },
    })
    expect(wrapper.find('[data-test="phase-completed"]').classes()).toContain('active')
  })
})

describe('RunActionsPanel', () => {
  it('enables Pause + Cancel for a running run', () => {
    const wrapper = mount(RunActionsPanel, {
      ...globalConfig,
      props: { run: makeRun({ state: 'running' }) },
    })
    expect(wrapper.find('[data-test="action-pause"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-test="action-resume"]').attributes('disabled')).toBe('')
    expect(wrapper.find('[data-test="action-cancel"]').attributes('disabled')).toBeUndefined()
  })

  it('enables Resume + Cancel for a paused run', () => {
    const wrapper = mount(RunActionsPanel, {
      ...globalConfig,
      props: { run: makeRun({ state: 'paused' }) },
    })
    expect(wrapper.find('[data-test="action-pause"]').attributes('disabled')).toBe('')
    expect(wrapper.find('[data-test="action-resume"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-test="action-cancel"]').attributes('disabled')).toBeUndefined()
  })

  it('disables everything once the run is completed', () => {
    const wrapper = mount(RunActionsPanel, {
      ...globalConfig,
      props: { run: makeRun({ state: 'completed' }) },
    })
    expect(wrapper.find('[data-test="action-pause"]').attributes('disabled')).toBe('')
    expect(wrapper.find('[data-test="action-resume"]').attributes('disabled')).toBe('')
    expect(wrapper.find('[data-test="action-cancel"]').attributes('disabled')).toBe('')
  })

  it('requires a confirm before emitting pause', async () => {
    const wrapper = mount(RunActionsPanel, {
      ...globalConfig,
      props: { run: makeRun({ state: 'running' }) },
    })
    await wrapper.find('[data-test="action-pause"]').trigger('click')
    expect(wrapper.find('[data-test="confirm-dialog"]').exists()).toBe(true)
    expect(wrapper.emitted('pause')).toBeFalsy()
    await wrapper.find('[data-test="confirm-ok"]').trigger('click')
    expect(wrapper.emitted('pause')).toBeTruthy()
  })

  it('lets the operator dismiss the confirm without acting', async () => {
    const wrapper = mount(RunActionsPanel, {
      ...globalConfig,
      props: { run: makeRun({ state: 'running' }) },
    })
    await wrapper.find('[data-test="action-cancel"]').trigger('click')
    await wrapper.find('[data-test="confirm-cancel"]').trigger('click')
    expect(wrapper.emitted('cancel')).toBeFalsy()
  })

  it('emits resume directly without confirm', async () => {
    const wrapper = mount(RunActionsPanel, {
      ...globalConfig,
      props: { run: makeRun({ state: 'paused' }) },
    })
    await wrapper.find('[data-test="action-resume"]').trigger('click')
    expect(wrapper.emitted('resume')).toBeTruthy()
  })

  it('shows the next-action hint when paused', () => {
    const wrapper = mount(RunActionsPanel, {
      ...globalConfig,
      props: {
        run: makeRun({ state: 'paused' }),
        nextActionHint: 'Insérer le stylo Cyan dans le slot #3.',
      },
    })
    expect(wrapper.find('[data-test="next-action-hint"]').text()).toContain('Cyan')
  })

  it('hides the hint when not paused even if provided', () => {
    const wrapper = mount(RunActionsPanel, {
      ...globalConfig,
      props: {
        run: makeRun({ state: 'running' }),
        nextActionHint: 'Insérer le stylo Cyan.',
      },
    })
    expect(wrapper.find('[data-test="next-action-hint"]').exists()).toBe(false)
  })
})
