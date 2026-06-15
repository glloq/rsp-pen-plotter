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
    expect(pipe.status.value).toBe('resolver-error')
    expect(deps.ensureSegmentation).not.toHaveBeenCalled()
    expect(render).not.toHaveBeenCalled()
    // A resolver error keeps the previous decision intact, so generating from
    // the last good decision stays allowed (the modal's own decision-null
    // check is what gates the very first resolve).
    expect(pipe.canGenerate.value).toBe(true)
  })

  it('catches a segmentation error: surfaces it, clears the spinner, no unhandled rejection', async () => {
    const render = stubRender()
    const ensureSegmentation = vi.fn().mockImplementation(async (_d, _c, onUploadStart) => {
      // Simulate ``ensureSelectedFile`` having flipped the spinner before
      // the upload threw — the bug was this leaving previewLoading stuck.
      onUploadStart()
      throw new Error('upload failed')
    })
    const deps = makeDeps({ ensureSegmentation })
    const pipe = useEditorPreviewPipeline(deps)

    pipe.schedule('resolve-and-segment', { immediate: true })
    await flushPromises()

    expect(ensureSegmentation).toHaveBeenCalledTimes(1)
    // Render never runs after a failed segmentation.
    expect(render).not.toHaveBeenCalled()
    // The error is surfaced and the pipeline lands in a terminal state with
    // no lingering spinner.
    expect(pipe.previewError.value).toBe(true)
    expect(pipe.previewErrorMessage.value).toBe('upload failed')
    expect(pipe.status.value).toBe('segmentation-error')
    expect(pipe.previewLoading.value).toBe(false)
    expect(pipe.resolving.value).toBe(false)
    expect(pipe.busy.value).toBe(false)
    // A segmentation error leaves the placement out of sync with the freshly
    // resolved decision — Generate must stay blocked (audit P1).
    expect(pipe.canGenerate.value).toBe(false)
  })

  it('a later flush after a segmentation error recovers (status back to idle)', async () => {
    const render = stubRender()
    const ensureSegmentation = vi
      .fn()
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValue(undefined)
    const pipe = useEditorPreviewPipeline(makeDeps({ ensureSegmentation }))

    pipe.schedule('resolve-and-segment', { immediate: true })
    await flushPromises()
    expect(pipe.status.value).toBe('segmentation-error')

    pipe.schedule('resolve-and-segment', { immediate: true })
    await flushPromises()
    expect(pipe.previewError.value).toBe(false)
    expect(pipe.status.value).toBe('idle')
    expect(pipe.canGenerate.value).toBe(true)
    expect(render).toHaveBeenCalledTimes(1)
  })

  it('does not surface a segmentation error when the flush was aborted', async () => {
    stubRender()
    let rejectSeg!: (e: Error) => void
    const ensureSegmentation = vi.fn().mockImplementation(
      () =>
        new Promise<void>((_resolve, reject) => {
          rejectSeg = reject
        }),
    )
    const pipe = useEditorPreviewPipeline(makeDeps({ ensureSegmentation }))

    pipe.schedule('resolve-and-segment', { immediate: true })
    await flushPromises() // resolve done, awaiting segmentation
    // A newer immediate flush aborts the first controller, then the first
    // segmentation rejects — it must NOT paint an error over the new run.
    pipe.schedule('resolve-and-segment', { immediate: true })
    rejectSeg(new Error('stale failure'))
    await flushPromises()

    expect(pipe.previewError.value).toBe(false)
    expect(pipe.previewErrorMessage.value).toBeNull()
  })

  it('returns to an idle, not-busy status after a successful flush', async () => {
    stubRender()
    const pipe = useEditorPreviewPipeline(makeDeps())
    expect(pipe.status.value).toBe('idle')

    pipe.schedule('resolve-and-segment', { immediate: true })
    await flushPromises()

    expect(pipe.status.value).toBe('idle')
    expect(pipe.busy.value).toBe(false)
  })

  it('is busy (Generate locked) during the debounce window before a flush fires', async () => {
    stubRender()
    const pipe = useEditorPreviewPipeline(makeDeps())
    expect(pipe.busy.value).toBe(false)
    expect(pipe.canGenerate.value).toBe(true)

    // A debounced schedule (ink / style / size tweak) must lock Generate
    // *immediately*, not only once flush() starts — otherwise the operator
    // can generate against a preview that hasn't begun catching up (audit P1).
    pipe.schedule('render-only')
    expect(pipe.busy.value).toBe(true)
    expect(pipe.canGenerate.value).toBe(false)

    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()
    expect(pipe.busy.value).toBe(false)
    expect(pipe.canGenerate.value).toBe(true)
  })

  it('a render error stays generate-safe (placement still matches the decision)', async () => {
    const job = useJobStore()
    vi.spyOn(job, 'previewAlgorithmOnAllLayers').mockRejectedValue(new Error('render down'))
    const pipe = useEditorPreviewPipeline(makeDeps())

    pipe.schedule('resolve-and-segment', { immediate: true })
    await flushPromises()

    // Segmentation landed; only the preview render failed — the placement is
    // consistent with the decision, so generating from it is still allowed.
    expect(pipe.previewError.value).toBe(true)
    expect(pipe.status.value).toBe('render-error')
    expect(pipe.busy.value).toBe(false)
    expect(pipe.canGenerate.value).toBe(true)
  })

  it('dispose() clears the pending level so a torn-down pipeline reads not-busy', async () => {
    stubRender()
    const pipe = useEditorPreviewPipeline(makeDeps())

    pipe.schedule('render-only') // debounced, queues a pending level
    expect(pipe.busy.value).toBe(true)
    pipe.dispose()
    expect(pipe.busy.value).toBe(false)
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
