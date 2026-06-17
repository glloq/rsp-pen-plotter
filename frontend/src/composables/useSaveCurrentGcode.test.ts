// @vitest-environment happy-dom
import { createPinia, setActivePinia, storeToRefs } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import type { GcodeFileSummary, MachineProfile } from '../api/client'

// Hoisted fake backend so the api mock and the assertions share state.
const h = vi.hoisted(() => ({ saveGcodeFile: vi.fn() }))

vi.mock('../api/client', async (orig) => {
  const actual = await orig<typeof import('../api/client')>()
  return {
    ...actual,
    listGcodeFiles: vi.fn(async () => []),
    listAvailableColors: vi.fn(async () => []),
    saveGcodeFile: h.saveGcodeFile,
  }
})

import { useSaveCurrentGcode } from './useSaveCurrentGcode'
import { useJobStore } from '../stores/job'
import { useAvailableColorsStore } from '../stores/availableColors'

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
    job.gcode = 'G1 X0\nG1 X1'
    await nextTick()
  }
  return job
}

describe('useSaveCurrentGcode', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    h.saveGcodeFile.mockReset()
    h.saveGcodeFile.mockImplementation(
      async (name: string): Promise<GcodeFileSummary> => ({
        id: 'new1',
        name,
        profile_name: 'P',
        line_count: 2,
        size_bytes: 10,
        length_mm_by_color: {},
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      }),
    )
  })

  it('saves the current program with its name, profile and G-code', async () => {
    const job = await seedJob(true)
    const { canSave, saveCurrent } = useSaveCurrentGcode()
    expect(canSave.value).toBe(true)

    const created = await saveCurrent()
    // No source file is loaded in this fixture, so it falls back to 'gcode'.
    // No placements either → empty per-colour lengths.
    expect(h.saveGcodeFile).toHaveBeenCalledWith('gcode', job.selectedProfileName, job.gcode, {})
    expect(created?.id).toBe('new1')
  })

  it('is a no-op when there is no G-code', async () => {
    await seedJob(false)
    const { canSave, saveCurrent } = useSaveCurrentGcode()
    expect(canSave.value).toBe(false)

    const created = await saveCurrent()
    expect(created).toBeNull()
    expect(h.saveGcodeFile).not.toHaveBeenCalled()
  })

  it('never advances the ink odometer on save', async () => {
    await seedJob(true)
    const colors = useAvailableColorsStore()
    const odo = vi.spyOn(colors, 'addToOdometer').mockResolvedValue()
    const { saveCurrent } = useSaveCurrentGcode()

    await saveCurrent()

    // Saving stores the program but must not touch ink accounting — that
    // happens only when a plot is actually launched.
    expect(h.saveGcodeFile).toHaveBeenCalled()
    expect(odo).not.toHaveBeenCalled()
  })
})
