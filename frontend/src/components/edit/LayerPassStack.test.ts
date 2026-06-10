// @vitest-environment happy-dom
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it } from 'vitest'
import LayerPassStack from './LayerPassStack.vue'
import type { LayerPass } from '../../stores/job'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
})

function makePasses(): LayerPass[] {
  return [
    { algorithm: 'crosshatch', algorithm_options: { angle_deg: 45 } },
    { algorithm: 'stippling', algorithm_options: { density: 0.02 } },
  ]
}

function mountStack(passes: LayerPass[]) {
  return mount(LayerPassStack, {
    props: { passes, layerId: 'layer-1' },
    global: { plugins: [i18n] },
  })
}

function lastUpdate(wrapper: ReturnType<typeof mountStack>): LayerPass[] {
  const events = wrapper.emitted('update')
  expect(events).toBeTruthy()
  return events!.at(-1)![0] as LayerPass[]
}

describe('LayerPassStack visibility toggle', () => {
  it('keeps a hidden pass in the emitted stack (enabled: false)', async () => {
    const wrapper = mountStack(makePasses())
    await wrapper.find('[data-test="pass-toggle-0"]').trigger('click')
    const emitted = lastUpdate(wrapper)
    // Non-destructive: BOTH passes are still present.
    expect(emitted).toHaveLength(2)
    expect(emitted[0]!.enabled).toBe(false)
    expect(emitted[0]!.algorithm).toBe('crosshatch')
    expect(emitted[1]!.enabled).toBeUndefined()
  })

  it('re-enables a hidden pass on the second click', async () => {
    const wrapper = mountStack(makePasses())
    await wrapper.find('[data-test="pass-toggle-0"]').trigger('click')
    // Simulate the parent feeding the updated stack back in.
    await wrapper.setProps({ passes: lastUpdate(wrapper) })
    await wrapper.find('[data-test="pass-toggle-0"]').trigger('click')
    const emitted = lastUpdate(wrapper)
    expect(emitted).toHaveLength(2)
    expect(emitted[0]!.enabled).toBe(true)
  })
})

describe('LayerPassStack stack mutations', () => {
  it('duplicate emits the full stack including hidden rows', async () => {
    const passes = makePasses()
    passes[0]!.enabled = false
    const wrapper = mountStack(passes)
    await wrapper.find('[data-test="pass-duplicate-1"]').trigger('click')
    const emitted = lastUpdate(wrapper)
    expect(emitted).toHaveLength(3)
    // The hidden row survives the mutation untouched.
    expect(emitted[0]!.enabled).toBe(false)
    expect(emitted[1]!.algorithm).toBe('stippling')
    expect(emitted[2]!.algorithm).toBe('stippling')
    // The copy is a fresh object, not a shared reference.
    expect(emitted[2]).not.toBe(emitted[1])
  })

  it('remove drops exactly the targeted row and keeps hidden state of the rest', async () => {
    const passes = makePasses()
    passes[1]!.enabled = false
    const wrapper = mountStack(passes)
    await wrapper.find('[data-test="pass-remove-0"]').trigger('click')
    const emitted = lastUpdate(wrapper)
    expect(emitted).toHaveLength(1)
    expect(emitted[0]!.algorithm).toBe('stippling')
    expect(emitted[0]!.enabled).toBe(false)
  })

  it('renders hidden rows with the strike-through affordance', () => {
    const passes = makePasses()
    passes[0]!.enabled = false
    const wrapper = mountStack(passes)
    const toggle = wrapper.find('[data-test="pass-toggle-0"]')
    expect(toggle.text()).toBe('◌')
    expect(wrapper.find('[data-test="pass-toggle-1"]').text()).toBe('●')
  })
})
