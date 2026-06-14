// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { useAvailableColorsStore } from '../stores/availableColors'
import { useJobStore } from '../stores/job'
import { usePaletteSourceStore } from '../stores/paletteSource'
import {
  useEditorPaletteSegmentation,
  type SegmentationFileManager,
} from './useEditorPaletteSegmentation'

const POOL = ['#ff0000', '#00ff00', '#0000ff']

const FIXED_PALETTE_DECISION = {
  segmentation_method: 'fixed_palette',
  default_algorithm: 'scanlines',
  default_options: {},
  default_passes: [],
  quality_tier: 'draft',
  fallback_chain: [],
  reasoning: [],
  hard_constraints_applied: [],
}

function seedInventory(hexes: string[]) {
  const inventory = useAvailableColorsStore()
  inventory.colors = hexes.map((hex, i) => ({
    color_id: `id-${i}`,
    hex,
    name: `c${i}`,
    position: i,
    stroke_width_mm: 0.5,
    odometer_mm: 0,
    created_at: '',
  }))
}

function seedImagePlacement(lastOptions: Record<string, unknown>) {
  const job = useJobStore()
  const id = job.addEmptyPlacement()
  const file = new File(['x'], 'photo.jpg', { type: 'image/jpeg' })
  job.placements = job.placements.map((p) =>
    p.id === id
      ? { ...p, source_file: 'photo.jpg', source_mime: 'image/jpeg', last_file: file, last_options: lastOptions }
      : p,
  )
  return file
}

function fakeFileManager(file: File | null): SegmentationFileManager {
  return {
    ensureSelectedFile: vi.fn().mockResolvedValue(undefined),
    selectedFile: ref(file),
    buildOptions: () => ({ drop_background: true }),
  }
}

describe('useEditorPaletteSegmentation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('re-uploads with kmeans_lab + ink_pool when the cached pool differs', async () => {
    usePaletteSourceStore().source = 'union'
    seedInventory(POOL)
    const file = seedImagePlacement({ segmentation_method: 'kmeans', num_colors: 4 })
    const job = useJobStore()
    const upload = vi.spyOn(job, 'upload').mockResolvedValue()

    const seg = useEditorPaletteSegmentation(fakeFileManager(file))
    const onUploadStart = vi.fn()
    await seg.ensureSegmentationMatchesDecision(
      FIXED_PALETTE_DECISION as never,
      new AbortController(),
      onUploadStart,
    )

    expect(onUploadStart).toHaveBeenCalledTimes(1)
    expect(upload).toHaveBeenCalledTimes(1)
    const [, options] = upload.mock.calls[0]!
    // pool size 3 + 1 background cluster (drop_background default).
    expect(options).toMatchObject({
      segmentation_method: 'kmeans_lab',
      ink_pool: POOL,
      num_colors: 4,
    })
  })

  it('skips the re-upload when the cached options already match the pool', async () => {
    usePaletteSourceStore().source = 'union'
    seedInventory(POOL)
    const file = seedImagePlacement({ segmentation_method: 'kmeans_lab', ink_pool: POOL })
    const job = useJobStore()
    const upload = vi.spyOn(job, 'upload').mockResolvedValue()

    const seg = useEditorPaletteSegmentation(fakeFileManager(file))
    await seg.ensureSegmentationMatchesDecision(FIXED_PALETTE_DECISION as never, new AbortController())

    expect(upload).not.toHaveBeenCalled()
  })

  it('is a no-op when the decision is not a fixed_palette split', async () => {
    usePaletteSourceStore().source = 'union'
    seedInventory(POOL)
    const file = seedImagePlacement({ segmentation_method: 'kmeans', num_colors: 4 })
    const job = useJobStore()
    const upload = vi.spyOn(job, 'upload').mockResolvedValue()

    const seg = useEditorPaletteSegmentation(fakeFileManager(file))
    await seg.ensureSegmentationMatchesDecision(
      { ...FIXED_PALETTE_DECISION, segmentation_method: 'kmeans_lab' } as never,
      new AbortController(),
    )

    expect(upload).not.toHaveBeenCalled()
  })

  it('skips a re-upload when the pool has fewer than two colours', async () => {
    usePaletteSourceStore().source = 'union'
    seedInventory(['#ff0000'])
    const file = seedImagePlacement({ segmentation_method: 'kmeans', num_colors: 4 })
    const job = useJobStore()
    const upload = vi.spyOn(job, 'upload').mockResolvedValue()

    const seg = useEditorPaletteSegmentation(fakeFileManager(file))
    await seg.ensureSegmentationMatchesDecision(FIXED_PALETTE_DECISION as never, new AbortController())

    expect(upload).not.toHaveBeenCalled()
  })
})
