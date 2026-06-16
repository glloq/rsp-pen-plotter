// @vitest-environment happy-dom
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { createI18n } from 'vue-i18n'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import type { GcodeFileSummary, PrintRun } from '../api/client'

// Shared, hoisted fake backend state so the api mock and the tests can
// both reach it (vi.mock is hoisted above the imports).
const h = vi.hoisted(() => ({
  files: [] as GcodeFileSummary[],
  saveGcodeFile: vi.fn(),
  printGcodeFile: vi.fn(),
  deleteGcodeFile: vi.fn(),
  renameGcodeFile: vi.fn(),
}))

vi.mock('../api/client', async (orig) => {
  const actual = await orig<typeof import('../api/client')>()
  return {
    ...actual,
    listQueue: vi.fn(async () => []),
    listGcodeFiles: vi.fn(async () => h.files.slice()),
    saveGcodeFile: h.saveGcodeFile,
    printGcodeFile: h.printGcodeFile,
    deleteGcodeFile: h.deleteGcodeFile,
    renameGcodeFile: h.renameGcodeFile,
  }
})

vi.mock('../composables/confirm', () => ({ confirmAction: vi.fn(async () => true) }))

import en from '../locales/en.json'
import GcodeFilesPanel from './GcodeFilesPanel.vue'
import { useJobStore } from '../stores/job'
import { useQueueStore } from '../stores/queue'
import type { MachineProfile } from '../api/client'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en },
})

function fileSummary(over: Partial<GcodeFileSummary> = {}): GcodeFileSummary {
  return {
    id: 'f1',
    name: 'mon-dessin',
    profile_name: 'P',
    line_count: 4,
    size_bytes: 120,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  }
}

function makeProfile(): MachineProfile {
  return {
    name: 'P',
    pen_slot_count: 1,
    workspace: { x_min: 0, y_min: 0, x_max: 1, y_max: 1 },
  } as MachineProfile
}

async function seedJob(withGcode: boolean): Promise<ReturnType<typeof useJobStore>> {
  const job = useJobStore()
  const { profiles, selectedProfileName } = storeToRefs(job)
  profiles.value = [makeProfile()]
  selectedProfileName.value = 'P'
  await nextTick()
  if (withGcode) {
    // Set after the profile-change invalidation watcher has fired.
    job.gcode = 'G1 X0\nG1 X1\nG1 X2\nG1 X3'
    await nextTick()
  }
  return job
}

function mountPanel() {
  return mount(GcodeFilesPanel, { global: { plugins: [i18n] } })
}

describe('GcodeFilesPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    h.files = []
    h.saveGcodeFile.mockReset()
    h.printGcodeFile.mockReset()
    h.deleteGcodeFile.mockReset()
    h.renameGcodeFile.mockReset()
    h.saveGcodeFile.mockImplementation(async (name: string) => {
      const created = fileSummary({ id: 'new1', name })
      h.files.push(created)
      return created
    })
    h.printGcodeFile.mockResolvedValue({
      id: 'run1',
      gcode_file_id: 'f1',
      state: 'queued',
    } as PrintRun)
    h.deleteGcodeFile.mockImplementation(async (id: string) => {
      h.files = h.files.filter((f) => f.id !== id)
    })
    h.renameGcodeFile.mockImplementation(async (id: string, name: string) =>
      fileSummary({ id, name }),
    )
  })

  it('shows a generate-first hint and no save button when there is no G-code', async () => {
    await seedJob(false)
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.find('[data-test="gcode-save-current"]').exists()).toBe(false)
    expect(wrapper.text()).toContain(en.gcodeFiles.generateFirst)
  })

  it('saves the current program into the library and selects it', async () => {
    const job = await seedJob(true)
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.find('[data-test="gcode-save-current"]').trigger('click')
    await flushPromises()

    expect(h.saveGcodeFile).toHaveBeenCalledWith('gcode', job.selectedProfileName, job.gcode)
    // The new file appears and is auto-selected → Print is enabled.
    expect(wrapper.find('[data-test="gcode-file-new1"]').exists()).toBe(true)
    const printBtn = wrapper.find('[data-test="gcode-print-selected"]')
    expect(printBtn.attributes('disabled')).toBeUndefined()
  })

  it('prints the selected file on demand', async () => {
    h.files = [fileSummary({ id: 'f1', name: 'logo' })]
    await seedJob(false)
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.find('[data-test="gcode-file-select-f1"]').trigger('click')
    await nextTick()
    await wrapper.find('[data-test="gcode-print-selected"]').trigger('click')
    await flushPromises()

    expect(h.printGcodeFile).toHaveBeenCalledWith('f1')
  })

  it('shows the live state inline for a file that is printing, and blocks its actions', async () => {
    h.files = [fileSummary({ id: 'f1', name: 'logo' })]
    await seedJob(false)
    const queue = useQueueStore()
    storeToRefs(queue).runs.value = [
      { id: 'run1', name: 'logo', gcode_file_id: 'f1', state: 'running' } as PrintRun,
    ]
    const wrapper = mountPanel()
    await flushPromises()

    const state = wrapper.find('[data-test="gcode-file-state-f1"]')
    expect(state.exists()).toBe(true)
    expect(state.text()).toBe(en.queue.state.running)
    // A printing file can't be selected-and-printed again or deleted.
    await wrapper.find('[data-test="gcode-file-select-f1"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="gcode-print-selected"]').attributes('disabled')).toBeDefined()
  })

  it('deletes a file after confirmation', async () => {
    h.files = [fileSummary({ id: 'f1', name: 'logo' })]
    await seedJob(false)
    const wrapper = mountPanel()
    await flushPromises()

    await wrapper.find('[data-test="gcode-file-f1"] button[aria-label="Delete"]').trigger('click')
    await flushPromises()

    expect(h.deleteGcodeFile).toHaveBeenCalledWith('f1')
  })
})
