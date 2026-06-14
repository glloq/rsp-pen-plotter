// @vitest-environment happy-dom
import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

vi.mock('../domain/policy/client', () => ({
  resolveAlgorithmPolicy: vi.fn(),
}))

import { resolveAlgorithmPolicy } from '../domain/policy/client'
import { useJobStore } from '../stores/job'
import { useEditorPreviewPipeline, type PreviewPipelineDeps } from './useEditorPreviewPipeline'

const DECISION = {
  segmentation_method: 'fixed_palette',
  default_algorithm: 'scanlines',
  default_options: { spacing_px: 5 },
  default_passes: [],
  quality_tier: 'draft',
  fallback_chain: [],
  reasoning: [],
  hard_constraints_applied: [],
}

function makeDeps(over: Partial<PreviewPipelineDeps> = {}): PreviewPipelineDeps {
  return {
    hasPlacement: ref(true),
    sourceKind: ref('bitmap_photo'),
    goal: ref('balanced'),
    paletteMode: ref('free'),
    customStylesActive: ref(false),
    customPasses: ref([]),
    resolveInputs: () => ({
      available_colors_count: 1,
      image_megapixels: null,
      layer_count_estimate: 1,
      is_mono_pen_machine: false,
    }),
    ensureSegmentation: vi.fn().mockResolvedValue(undefined),
    ...over,
  }
}

describe('useEditorPreviewPipeline', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.mocked(resolveAlgorithmPolicy).mockReset()
    vi.mocked(resolveAlgorithmPolicy).mockResolvedValue(DECISION as never)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  function stubRender() {
    const job = useJobStore()
    const render = vi
      .spyOn(job, 'previewAlgorithmOnAllLayers')
      .mockResolvedValue({ svg: '<svg data-x="adapted"/>', warnings: [] })
    return render
  }

  it('resolve-and-segment runs resolve → segment → render and stores the svg', async () => {
    const render = stubRender()
    const deps = makeDeps()
    const pipe = useEditorPreviewPipeline(deps)

    pipe.schedule('resolve-and-segment', { immediate: true })
    await flushPromises()

    expect(resolveAlgorithmPolicy).toHaveBeenCalledTimes(1)
    expect(deps.ensureSegmentation).toHaveBeenCalledTimes(1)
    expect(render).toHaveBeenCalledTimes(1)
    expect(pipe.decision.value).toMatchObject({ default_algorithm: 'scanlines' })
    expect(pipe.renderedSvg.value).toBe('<svg data-x="adapted"/>')
    expect(pipe.previewLoading.value).toBe(false)
  })

  it('merges a render-only + resolve-and-segment burst into ONE resolve at the strongest level', async () => {
    const render = stubRender()
    const pipe = useEditorPreviewPipeline(makeDeps())

    // A slider tick (render-only) and a pool edit (resolve-and-segment) in
    // the same beat — must collapse to a single resolve, not two renders.
    pipe.schedule('render-only')
    pipe.schedule('resolve-and-segment')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(resolveAlgorithmPolicy).toHaveBeenCalledTimes(1)
    expect(render).toHaveBeenCalledTimes(1)
  })

  it('an immediate request supersedes a pending debounced one (no double render)', async () => {
    const render = stubRender()
    const pipe = useEditorPreviewPipeline(makeDeps())

    pipe.schedule('resolve-and-segment') // debounced
    pipe.schedule('resolve-and-segment', { immediate: true }) // clears the timer, flushes now
    await flushPromises()
    // Let any (wrongly) surviving timer fire.
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(resolveAlgorithmPolicy).toHaveBeenCalledTimes(1)
    expect(render).toHaveBeenCalledTimes(1)
  })

  it('render-only re-renders WITHOUT re-resolving once a decision exists', async () => {
    const render = stubRender()
    const pipe = useEditorPreviewPipeline(makeDeps())

    pipe.schedule('resolve-and-segment', { immediate: true })
    await flushPromises()
    expect(resolveAlgorithmPolicy).toHaveBeenCalledTimes(1)
    expect(render).toHaveBeenCalledTimes(1)

    pipe.schedule('render-only')
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    // No second resolve; one extra render.
    expect(resolveAlgorithmPolicy).toHaveBeenCalledTimes(1)
    expect(render).toHaveBeenCalledTimes(2)
  })

  it('skips entirely when there is no placement', async () => {
    const render = stubRender()
    const pipe = useEditorPreviewPipeline(makeDeps({ hasPlacement: ref(false) }))

    pipe.schedule('resolve-and-segment', { immediate: true })
    await flushPromises()

    expect(resolveAlgorithmPolicy).not.toHaveBeenCalled()
    expect(render).not.toHaveBeenCalled()
  })

  it('surfaces resolver errors in resolveError and stops before rendering', async () => {
    const render = stubRender()
    vi.mocked(resolveAlgorithmPolicy).mockRejectedValueOnce(new Error('boom'))
    const deps = makeDeps()
    const pipe = useEditorPreviewPipeline(deps)

    pipe.schedule('resolve-and-segment', { immediate: true })
    await flushPromises()

    expect(pipe.resolveError.value).toBe('boom')
    expect(pipe.resolving.value).toBe(false)
    expect(deps.ensureSegmentation).not.toHaveBeenCalled()
    expect(render).not.toHaveBeenCalled()
  })

  it('dispose() cancels a pending debounced flush', async () => {
    const render = stubRender()
    const pipe = useEditorPreviewPipeline(makeDeps())

    pipe.schedule('resolve-and-segment') // debounced, not yet fired
    pipe.dispose()
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(resolveAlgorithmPolicy).not.toHaveBeenCalled()
    expect(render).not.toHaveBeenCalled()
  })
})
