import { afterEach, describe, expect, it, vi } from 'vitest'
import { runGeneratePipeline } from './runGeneratePipeline'
import * as client from '../api/client'
import type { PrintPlan } from '../domain/print-plan'

function makePlan(): PrintPlan {
  return {
    svg: '<svg xmlns="http://www.w3.org/2000/svg"/>',
    profile_name: 'Test',
    layers: [],
    scale_mode: 'fit',
    margin_mm: 0,
    placement: null,
    metadata: { client_version: 'test', created_at: new Date().toISOString() },
  }
}

function makeDeps(overrides: Partial<Parameters<typeof runGeneratePipeline>[0]> = {}) {
  return {
    placements: [],
    applyOptimized: vi.fn(),
    buildPlan: () => makePlan(),
    onPhase: vi.fn(),
    onMetrics: vi.fn(),
    signal: new AbortController().signal,
    ...overrides,
  }
}

describe('runGeneratePipeline — missing pen slots', () => {
  afterEach(() => vi.restoreAllMocks())

  it('asks the operator on 409 and retries with allow_missing_slots=true', async () => {
    // First /generate call → 409 with structured detail; second call
    // (after the operator confirms) must carry the override.
    const error = {
      response: {
        status: 409,
        data: {
          detail: { reason: 'missing_pen_slots', slots: [2, 7], message: '...' },
        },
      },
    }
    const generate = vi
      .spyOn(client, 'generateGcode')
      .mockRejectedValueOnce(error)
      .mockResolvedValueOnce({
        gcode: 'G21',
        line_count: 1,
        plan_hash: 'hash-x',
        resolved_plan: {} as never,
      })
    vi.spyOn(client, 'preflightCheck').mockResolvedValue({
      ok: true,
      within_bounds: true,
      width_mm: 100,
      height_mm: 100,
      scale: 1,
      drawing_length_mm: 0,
      travel_length_mm: 0,
      estimated_seconds: 0,
      pen_changes: 0,
      layer_count: 0,
      path_count: 0,
      missing_pen_slots: [],
      warnings: [],
      plan_hash: 'hash-x',
    })
    const confirmMissingPenSlots = vi.fn().mockResolvedValue(true)

    const out = await runGeneratePipeline(makeDeps({ confirmMissingPenSlots }))

    expect(confirmMissingPenSlots).toHaveBeenCalledTimes(1)
    expect(confirmMissingPenSlots.mock.calls[0]?.[0]).toMatchObject({
      reason: 'missing_pen_slots',
      slots: [2, 7],
    })
    expect(generate).toHaveBeenCalledTimes(2)
    expect(generate.mock.calls[1]?.[2]).toEqual({ allowMissingSlots: true })
    expect(out.gcode).toBe('G21')
  })

  it('aborts the pipeline on 409 if the operator cancels', async () => {
    const error = {
      response: {
        status: 409,
        data: { detail: { reason: 'missing_pen_slots', slots: [3], message: '...' } },
      },
    }
    vi.spyOn(client, 'generateGcode').mockRejectedValueOnce(error)
    vi.spyOn(client, 'preflightCheck').mockResolvedValue({
      ok: true,
      within_bounds: true,
      width_mm: 0,
      height_mm: 0,
      scale: 1,
      drawing_length_mm: 0,
      travel_length_mm: 0,
      estimated_seconds: 0,
      pen_changes: 0,
      layer_count: 0,
      path_count: 0,
      missing_pen_slots: [],
      warnings: [],
      plan_hash: 'hash-x',
    })
    const confirmMissingPenSlots = vi.fn().mockResolvedValue(false)

    await expect(runGeneratePipeline(makeDeps({ confirmMissingPenSlots }))).rejects.toMatchObject({
      response: { status: 409 },
    })
  })

  it('does not intercept errors that are not the missing-slots 409', async () => {
    const error = {
      response: { status: 500, data: { detail: 'boom' } },
    }
    vi.spyOn(client, 'generateGcode').mockRejectedValueOnce(error)
    vi.spyOn(client, 'preflightCheck').mockResolvedValue({
      ok: true,
      within_bounds: true,
      width_mm: 0,
      height_mm: 0,
      scale: 1,
      drawing_length_mm: 0,
      travel_length_mm: 0,
      estimated_seconds: 0,
      pen_changes: 0,
      layer_count: 0,
      path_count: 0,
      missing_pen_slots: [],
      warnings: [],
      plan_hash: 'h',
    })
    const confirmMissingPenSlots = vi.fn()

    await expect(runGeneratePipeline(makeDeps({ confirmMissingPenSlots }))).rejects.toBe(error)
    expect(confirmMissingPenSlots).not.toHaveBeenCalled()
  })
})
