// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Hoisted fakes for the collaborators the launch flow drives. Mocking
// these keeps the test focused on the launch logic (gate → confirm → run
// → commit + the in-flight guard); the odometer maths live in
// useInkOdometer's own test.
const h = vi.hoisted(() => {
  const run = vi.fn()
  return {
    ensureMagazineLoaded: vi.fn(),
    confirmAction: vi.fn(),
    commitCurrentJob: vi.fn(),
    run,
    plotter: { status: { connected: true }, error: null as string | null, run },
  }
})

vi.mock('./magazineGate', () => ({ ensureMagazineLoaded: h.ensureMagazineLoaded }))
vi.mock('./confirm', () => ({ confirmAction: h.confirmAction }))
vi.mock('./useInkOdometer', () => ({
  useInkOdometer: () => ({ commitCurrentJob: h.commitCurrentJob }),
}))
vi.mock('../stores/plotter', () => ({ usePlotterStore: () => h.plotter }))

import { useLaunchCurrentJob } from './useLaunchCurrentJob'
import { useJobStore } from '../stores/job'

describe('useLaunchCurrentJob', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    h.ensureMagazineLoaded.mockReset().mockResolvedValue('skipped')
    h.confirmAction.mockReset().mockResolvedValue(true)
    h.commitCurrentJob.mockReset()
    h.run.mockReset().mockResolvedValue(undefined)
    h.plotter.status.connected = true
    h.plotter.error = null
    useJobStore().gcode = 'G1 X0'
  })

  it('runs the job and commits the odometer on a successful launch', async () => {
    const { launch } = useLaunchCurrentJob()
    await launch()
    expect(h.run).toHaveBeenCalledWith('G1 X0')
    expect(h.commitCurrentJob).toHaveBeenCalledTimes(1)
  })

  it('does NOT commit the odometer when the send fails', async () => {
    h.run.mockImplementation(async () => {
      h.plotter.error = 'boom'
    })
    const { launch } = useLaunchCurrentJob()
    await launch()
    expect(h.run).toHaveBeenCalled()
    expect(h.commitCurrentJob).not.toHaveBeenCalled()
  })

  it('does nothing when the magazine gate is cancelled', async () => {
    h.ensureMagazineLoaded.mockResolvedValue('cancelled')
    const { launch } = useLaunchCurrentJob()
    await launch()
    expect(h.run).not.toHaveBeenCalled()
    expect(h.commitCurrentJob).not.toHaveBeenCalled()
  })

  it('does nothing when the confirm dialog is declined', async () => {
    h.confirmAction.mockResolvedValue(false)
    const { launch } = useLaunchCurrentJob()
    await launch()
    expect(h.run).not.toHaveBeenCalled()
    expect(h.commitCurrentJob).not.toHaveBeenCalled()
  })

  it('does nothing while disconnected or without a G-code', async () => {
    const { launch } = useLaunchCurrentJob()
    h.plotter.status.connected = false
    await launch()
    expect(h.run).not.toHaveBeenCalled()

    h.plotter.status.connected = true
    useJobStore().gcode = ''
    await launch()
    expect(h.run).not.toHaveBeenCalled()
  })

  it('ignores a concurrent double-fire: one send, one commit', async () => {
    // Hold the gate open so both calls overlap in flight.
    let release: (v: string) => void = () => {}
    h.ensureMagazineLoaded.mockReturnValue(
      new Promise<string>((r) => {
        release = r
      }),
    )
    const { launch } = useLaunchCurrentJob()
    const first = launch()
    const second = launch() // blocked by the in-flight guard
    release('skipped')
    await Promise.all([first, second])
    expect(h.run).toHaveBeenCalledTimes(1)
    expect(h.commitCurrentJob).toHaveBeenCalledTimes(1)
  })
})
