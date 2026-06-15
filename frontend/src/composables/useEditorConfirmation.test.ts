import { describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'

import { useEditorConfirmation, type EditorConfirmationDeps } from './useEditorConfirmation'

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

function setup(over: Partial<EditorConfirmationDeps> = {}) {
  const onConfirm = vi.fn()
  const uploadSelected = vi.fn().mockResolvedValue(undefined)
  const deps: EditorConfirmationDeps = {
    isExpert: ref(false),
    hasPlacement: ref(true),
    decision: ref(DECISION as never),
    isDirty: ref(false),
    customStylesActive: ref(false),
    customPasses: ref([]),
    fileManager: { uploadSelected },
    onConfirm,
    ...over,
  }
  return { deps, onConfirm, uploadSelected, conf: useEditorConfirmation(deps) }
}

describe('useEditorConfirmation', () => {
  it('emits the decision directly in assisted mode', async () => {
    const { conf, onConfirm, uploadSelected } = setup()
    await conf.confirm()
    expect(uploadSelected).not.toHaveBeenCalled()
    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({ default_algorithm: 'scanlines' }),
    )
  })

  it('overrides the algorithm from the custom-style stack', async () => {
    const { conf, onConfirm } = setup({
      customStylesActive: ref(true),
      customPasses: ref([{ algorithm: 'halftone', algorithm_options: { dot: 2 } }]),
    })
    await conf.confirm()
    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({
        default_algorithm: 'halftone',
        default_options: { dot: 2 },
        default_passes: [{ algorithm: 'halftone', algorithm_options: { dot: 2 } }],
      }),
    )
  })

  it('does nothing without a placement or decision', async () => {
    const { conf, onConfirm } = setup({ decision: ref(null) })
    await conf.confirm()
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('expert + clean draft emits directly without uploading', async () => {
    const { conf, onConfirm, uploadSelected } = setup({ isExpert: ref(true), isDirty: ref(false) })
    await conf.confirm()
    expect(uploadSelected).not.toHaveBeenCalled()
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('expert + dirty draft awaits the upload before emitting confirm', async () => {
    let resolveUpload!: () => void
    const uploadSelected = vi.fn().mockReturnValue(
      new Promise<void>((resolve) => {
        resolveUpload = resolve
      }),
    )
    const { conf, onConfirm } = setup({
      isExpert: ref(true),
      isDirty: ref(true),
      fileManager: { uploadSelected },
    })

    const done = conf.confirm()
    await Promise.resolve()
    // Upload in flight → not emitted yet, buttons locked.
    expect(uploadSelected).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
    expect(conf.applying.value).toBe(true)

    resolveUpload()
    await done
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(conf.applying.value).toBe(false)
    expect(conf.applyError.value).toBeNull()
  })

  it('expert + dirty draft aborts confirm and surfaces the error when the upload fails', async () => {
    const uploadSelected = vi.fn().mockRejectedValue(new Error('network down'))
    const { conf, onConfirm } = setup({
      isExpert: ref(true),
      isDirty: ref(true),
      fileManager: { uploadSelected },
    })

    await conf.confirm()
    expect(onConfirm).not.toHaveBeenCalled()
    expect(conf.applyError.value).toBe('network down')
    expect(conf.applying.value).toBe(false)
  })

  it('ignores re-entrant confirm while an apply is already in flight', async () => {
    let resolveUpload!: () => void
    const uploadSelected = vi.fn().mockReturnValue(
      new Promise<void>((resolve) => {
        resolveUpload = resolve
      }),
    )
    const { conf, onConfirm } = setup({
      isExpert: ref(true),
      isDirty: ref(true),
      fileManager: { uploadSelected },
    })

    const first = conf.confirm()
    await Promise.resolve()
    await conf.confirm() // re-entrant: applying === true, should bail
    expect(uploadSelected).toHaveBeenCalledTimes(1)

    resolveUpload()
    await first
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('does not emit confirm if the modal is disposed while the upload is in flight', async () => {
    let resolveUpload!: () => void
    const uploadSelected = vi.fn().mockReturnValue(
      new Promise<void>((resolve) => {
        resolveUpload = resolve
      }),
    )
    const { conf, onConfirm } = setup({
      isExpert: ref(true),
      isDirty: ref(true),
      fileManager: { uploadSelected },
    })

    const done = conf.confirm()
    await Promise.resolve()
    expect(conf.applying.value).toBe(true)
    // Operator closes the modal mid-upload → host calls dispose().
    conf.dispose()
    resolveUpload()
    await done

    // The upload completed but confirm must NOT fire from the closed modal.
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('bails immediately when confirm is called after dispose', async () => {
    const { conf, onConfirm, uploadSelected } = setup()
    conf.dispose()
    await conf.confirm()
    expect(uploadSelected).not.toHaveBeenCalled()
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('expert isExpert reacts to a live ref (computed expert flag)', async () => {
    const mode = ref<'assisted' | 'expert'>('assisted')
    const uploadSelected = vi.fn().mockResolvedValue(undefined)
    const { conf, onConfirm } = setup({
      isExpert: computed(() => mode.value === 'expert'),
      isDirty: ref(true),
      fileManager: { uploadSelected },
    })

    // Assisted: no upload.
    await conf.confirm()
    expect(uploadSelected).not.toHaveBeenCalled()
    expect(onConfirm).toHaveBeenCalledTimes(1)

    // Flip to expert: now the dirty draft is committed first.
    mode.value = 'expert'
    await conf.confirm()
    expect(uploadSelected).toHaveBeenCalledTimes(1)
    expect(onConfirm).toHaveBeenCalledTimes(2)
  })
})
