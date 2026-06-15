// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { ref } from 'vue'

import { useEditorExpertPreview, type ExpertPreviewFileManager } from './useEditorExpertPreview'
import type { PreviewSnap } from './useEditorInkSwatches'
import { useJobStore } from '../stores/job'
import { useUiModeStore } from '../stores/uiMode'

function makeFileManager(over: Partial<ExpertPreviewFileManager> = {}): ExpertPreviewFileManager {
  return {
    previewSvg: ref(''),
    previewLoading: ref(false),
    selectedFilePlacementId: ref<string | null>(null),
    ...over,
  }
}

function seedPlacement(libraryFileId: string | null): string {
  const job = useJobStore()
  const id = job.addEmptyPlacement()
  job.placements = job.placements.map((p) =>
    p.id === id ? { ...p, library_file_id: libraryFileId ?? undefined } : p,
  )
  job.selectPlacement(id)
  return id
}

describe('useEditorExpertPreview', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('assisted mode falls back to the resolver render + pipeline loading', () => {
    const renderedSvg = ref<string | null>('<svg id="resolved"/>')
    const pipelineLoading = ref(true)
    const { effectivePreviewSvg, effectivePreviewLoading } = useEditorExpertPreview({
      fileManager: makeFileManager({ previewSvg: ref('<svg id="expert"/>') }),
      previewInkSnap: ref<PreviewSnap | null>(null),
      renderedSvg,
      pipelineLoading,
    })
    // Not expert → expert svg suppressed, resolver render shows.
    expect(effectivePreviewSvg.value).toBe('<svg id="resolved"/>')
    expect(effectivePreviewLoading.value).toBe(true)
  })

  it('expert mode forwards the /preview svg when the placement matches', () => {
    const id = seedPlacement(null)
    useUiModeStore().setMode('expert')
    const { effectivePreviewSvg, effectivePreviewLoading } = useEditorExpertPreview({
      fileManager: makeFileManager({
        previewSvg: ref('<svg id="expert"/>'),
        previewLoading: ref(true),
        selectedFilePlacementId: ref(id),
      }),
      previewInkSnap: ref<PreviewSnap | null>(null),
      renderedSvg: ref<string | null>('<svg id="resolved"/>'),
      pipelineLoading: ref(false),
    })
    expect(effectivePreviewSvg.value).toBe('<svg id="expert"/>')
    // Expert loading flows through even when the pipeline is idle.
    expect(effectivePreviewLoading.value).toBe(true)
  })

  it('expert mode suppresses a stale svg from a different placement', () => {
    seedPlacement(null) // active placement id = X
    useUiModeStore().setMode('expert')
    const { effectivePreviewSvg } = useEditorExpertPreview({
      fileManager: makeFileManager({
        previewSvg: ref('<svg id="stale"/>'),
        // File was loaded for a DIFFERENT (old) placement.
        selectedFilePlacementId: ref('some-other-id'),
      }),
      previewInkSnap: ref<PreviewSnap | null>(null),
      renderedSvg: ref<string | null>('<svg id="resolved"/>'),
      pipelineLoading: ref(false),
    })
    expect(effectivePreviewSvg.value).toBe('<svg id="resolved"/>')
  })

  it('sourceImageUrl is null without a library file and set with one', () => {
    seedPlacement(null)
    const noFile = useEditorExpertPreview({
      fileManager: makeFileManager(),
      previewInkSnap: ref<PreviewSnap | null>(null),
      renderedSvg: ref<string | null>(null),
      pipelineLoading: ref(false),
    })
    expect(noFile.sourceImageUrl.value).toBeNull()

    setActivePinia(createPinia())
    seedPlacement('lib-123')
    const withFile = useEditorExpertPreview({
      fileManager: makeFileManager(),
      previewInkSnap: ref<PreviewSnap | null>(null),
      renderedSvg: ref<string | null>(null),
      pipelineLoading: ref(false),
    })
    expect(withFile.sourceImageUrl.value).toContain('lib-123')
    expect(withFile.sourceImageUrl.value).toContain('preview-image')
  })
})
