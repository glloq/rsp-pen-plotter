// @vitest-environment happy-dom
//
// State-machine contract for the primary-action bar (UX vague 2): every
// combination of store signals maps to exactly one workflow step, in
// priority order (live run > import funnel > pens > generate > connect).
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useWorkflowStep } from './useWorkflowStep'
import { useJobStore } from '../stores/job'
import { useLibraryStore } from '../stores/library'
import { usePlotterStore } from '../stores/plotter'
import { useQueueStore } from '../stores/queue'
import type { LibraryFileRecord, PrintRun } from '../api/client'

function makeFile(id: string): LibraryFileRecord {
  return {
    file_id: id,
    sha256: id,
    source_file: `${id}.png`,
    source_mime: 'image/png',
    size_bytes: 10,
    layer_count: 1,
    folder: '',
    created_at: '2026-07-01T00:00:00Z',
  }
}

function makeRun(state: PrintRun['state']): PrintRun {
  return {
    id: 'r1',
    name: 'job',
    profile_name: 'p',
    total_lines: 10,
    acked_lines: 0,
    state,
    priority: 0,
    error: null,
    created_at: '',
    updated_at: '',
  } as PrintRun
}

// Minimal placement stub: the composable only reads svg / layers / id.
function seedPlacement(job: ReturnType<typeof useJobStore>, over: Record<string, unknown> = {}) {
  const placement = {
    id: 'p1',
    library_file_id: 'f1',
    is_library_draft: false,
    svg: '<svg/>',
    layers: [{ layer_id: 'l1' }],
    ...over,
  }
  // ``placements`` is a shallowRef — replace the array (like the store
  // does) instead of pushing, or the computed never re-evaluates.
  job.placements = [...job.placements, placement] as typeof job.placements
  return placement
}

describe('useWorkflowStep', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('walks the import funnel: empty → imported → placed', () => {
    const { step } = useWorkflowStep()
    expect(step.value).toBe('empty')

    const library = useLibraryStore()
    library.files = [makeFile('f1')]
    expect(step.value).toBe('imported')

    const job = useJobStore()
    seedPlacement(job, { svg: '', layers: [] })
    expect(step.value).toBe('placed')
  })

  it('styled placement without pens issues → configured; gcode → connect → ready', () => {
    const library = useLibraryStore()
    library.files = [makeFile('f1')]
    const job = useJobStore()
    seedPlacement(job)
    expect(useWorkflowStep().step.value).toBe('configured')

    job.gcode = 'G1 X1'
    expect(useWorkflowStep().step.value).toBe('ready_disconnected')

    const plotter = usePlotterStore()
    plotter.status.connected = true
    expect(useWorkflowStep().step.value).toBe('ready')
  })

  it('missing pens block the generate step', () => {
    const job = useJobStore()
    seedPlacement(job)
    vi.spyOn(job, 'missingPenSlots', 'get').mockReturnValue([2])
    expect(useWorkflowStep().step.value).toBe('preflight_blocked')
  })

  it('a live queue run overrides everything', () => {
    const queue = useQueueStore()
    queue.runs = [makeRun('running')]
    expect(useWorkflowStep().step.value).toBe('running')
    queue.runs = [makeRun('paused')]
    expect(useWorkflowStep().step.value).toBe('paused')
  })

  it('a direct serial run (no queue row) also flips to running', () => {
    const plotter = usePlotterStore()
    plotter.status.state = 'running'
    expect(useWorkflowStep().step.value).toBe('running')
  })
})
