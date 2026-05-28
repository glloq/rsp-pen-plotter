import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { errorDetail } from '../api/error'
import { i18n } from '../i18n'
import { validateUploadFile } from '../api/uploadValidation'
import { useLibraryStore } from './library'
import { usePerfStore } from './perf'
import { useToastStore } from './toasts'
import { useUiStore } from './ui'
import { useEditState } from '../composables/useEditState'
import { confirmAction } from '../composables/confirm'
import {
  deleteProfile as apiDeleteProfile,
  saveProfile as apiSaveProfile,
  downloadOriginalFile,
  getPresets,
  getProfiles,
  optimizeToolpaths,
  preflightCheck,
  rerenderJob,
  uploadFile,
  type BoundingBox,
  type Job,
  type LayerInfo,
  type MachineProfile,
  type Preset,
  type PreflightReport,
  type ToolpathMetrics,
} from '../api/client'
import { buildComposite } from '../lib/composite'
import { nearestPoolHex } from '../lib/nearestColor'
import { resolveEffectivePalette } from '../lib/effectivePalette'
import { usePaletteSourceStore } from './paletteSource'
import { useAvailableColorsStore } from './availableColors'
import { buildPrintPlan } from '../domain/plan-builder'
import { buildTypographyPlan } from '../composables/useBitmapDraft'
import type { PrintPlan } from '../domain/print-plan'
import {
  PipelineAbortedError,
  pipelineErrorMessage,
  runGeneratePipeline,
} from '../application/runGeneratePipeline'
import { attachScenePersistence } from '../infrastructure/storage/sceneStorage'

const DEFAULT_SPEED_MM_S = 60

// A placement is a fully self-contained snapshot: source file metadata,
// the rendered SVG, the per-layer config, and the position/size on the
// machine workspace. Multiple placements live side-by-side on the plan
// (different files OR multiple instances of the same file). The modal
// edits one at a time — ``selectedPlacementId``.
// One pass within a multi-pass layer override.
export interface LayerPass {
  algorithm: string
  algorithm_options: Record<string, unknown>
}

interface LayerAlgorithm {
  algorithm: string
  algorithm_options: Record<string, unknown>
  // Optional multi-pass stack. When present and non-empty, the backend
  // renders this layer as the ordered sequence of passes (each pass is
  // an algorithm + options pair drawn against the same colour mask),
  // letting a single ink show several visual treatments at once. Empty
  // / missing → legacy single-algorithm behaviour.
  passes?: LayerPass[]
}

// A variant is a named snapshot of the editor's per-layer choices for a
// placement: which algorithm to render each layer with, and whether the
// layer is currently visible. Switching variants pulls these into the
// placement's live state and triggers /rerender. The placement always
// has at least one variant; the active one IS the live state.
export interface Variant {
  id: string
  name: string
  layer_algorithms: Record<string, LayerAlgorithm>
  visibility: Record<string, boolean>
}

export interface Placement {
  id: string
  // Identifier of the library entry this placement draws from. Set whenever
  // the placement was created via the library (the canonical path); legacy
  // placements loaded from older localStorage scenes may have it ``null``.
  library_file_id: string | null
  source_file: string
  source_mime: string
  job_id: string | null
  // True when /rerender can re-run a different algorithm against a cached
  // bitmap segmentation. False for vector sources (SVG, PDF) where the
  // algorithm picker has no effect — the UI hides it in that case.
  rerenderable: boolean
  svg: string
  layers: LayerInfo[]
  source_bbox: BoundingBox
  layer_algorithms: Record<string, LayerAlgorithm>
  upload_warnings: string[]
  upload_metadata: Record<string, unknown>
  last_file: File | null
  last_options: Record<string, unknown> | undefined
  visibility: Record<string, boolean>
  x_mm: number
  y_mm: number
  width_mm: number
  height_mm: number
  // Quarter-turn rotation applied around the placement bbox centre.
  // Always normalized to 0/90/180/270.
  rotation: number
  // Horizontal / vertical mirroring, applied AFTER rotation.
  flip_h: boolean
  flip_v: boolean
  variants: Variant[]
  active_variant_id: string
  // True when this placement was created by "Edit from library" without
  // an explicit "Add to plan" — it's a working copy that holds the
  // operator's conversion-settings draft but is **not** rendered on the
  // sheet. ``visiblePlacements`` filters these out. Flipped to false when
  // the operator explicitly puts it on the plan.
  is_library_draft?: boolean
}

let placementCounter = 0
function newPlacementId(): string {
  placementCounter += 1
  return `p${Date.now().toString(36)}${placementCounter.toString(36)}`
}

function emptyBbox(): BoundingBox {
  return { x_min: 0, y_min: 0, x_max: 0, y_max: 0 }
}

export const useJobStore = defineStore('job', () => {
  // ====== Placements ====================================================
  const placements = ref<Placement[]>([])
  const selectedPlacementId = ref<string | null>(null)

  const selectedPlacement = computed<Placement | null>(() => {
    const id = selectedPlacementId.value
    if (!id) return null
    return placements.value.find((p) => p.id === id) ?? null
  })

  // Sheet-visible placements only — excludes "Edit from library" drafts
  // that hold conversion settings but aren't on the plan yet. Sheet
  // preview, simulator and FilesPane counters consume this view; the raw
  // ``placements`` list is for code that needs to see drafts too (the
  // editor itself, or the "is there already a draft for this file?" check).
  const visiblePlacements = computed<Placement[]>(() =>
    placements.value.filter((p) => !p.is_library_draft),
  )

  function patchPlacement(id: string, patch: Partial<Placement>): void {
    placements.value = placements.value.map((p) => (p.id === id ? { ...p, ...patch } : p))
    invalidateOutputs()
  }

  /** Promote a library-draft placement to a visible one. */
  function materializeLibraryDraft(id: string): void {
    patchPlacement(id, { is_library_draft: false })
  }
  function patchSelected(patch: Partial<Placement>): void {
    const id = selectedPlacementId.value
    if (!id) return
    patchPlacement(id, patch)
    preflight.value = null
  }

  // Persist a placement's variants back to the library so every future
  // placement of the same file starts from the latest snapshot. No-op
  // for placements without a library backing (legacy uploads).
  function syncPlacementToLibrary(p: Placement | null): void {
    if (!p?.library_file_id) return
    const library = useLibraryStore()
    // Persist the full editor config (``last_options``) alongside the
    // per-layer variants so the next "Edit from library" rehydrates the
    // operator's chosen segmentation / master style / preprocess instead
    // of resetting to defaults.
    library.saveFileVariants(p.library_file_id, p.variants, p.active_variant_id, p.last_options)
  }
  function syncSelectedToLibrary(): void {
    syncPlacementToLibrary(selectedPlacement.value)
  }

  function selectPlacement(id: string | null): void {
    selectedPlacementId.value = id
  }

  function removePlacement(id: string): void {
    placements.value = placements.value.filter((p) => p.id !== id)
    if (selectedPlacementId.value === id) {
      selectedPlacementId.value = placements.value[0]?.id ?? null
    }
    invalidateOutputs()
  }

  // Drop every placement (visible or "Edit from library" draft) backed by a
  // given library file. Called when the operator deletes the file from the
  // library so no orphaned placement lingers in the scene and silently
  // leaks back into the generated G-code (see buildPlanPayload). Without
  // this, deleting a file from the library left its placement on the plan,
  // so a later "add a different image + Generate" produced both drawings.
  function removePlacementsForFile(fileId: string): void {
    const before = placements.value.length
    placements.value = placements.value.filter((p) => p.library_file_id !== fileId)
    if (placements.value.length === before) return
    if (!placements.value.some((p) => p.id === selectedPlacementId.value)) {
      selectedPlacementId.value = placements.value.find((p) => !p.is_library_draft)?.id ?? null
    }
    invalidateOutputs()
  }

  function defaultPlacementSize(): {
    x_mm: number
    y_mm: number
    width_mm: number
    height_mm: number
  } {
    const ws = selectedProfile.value?.workspace
    if (!ws) return { x_mm: 0, y_mm: 0, width_mm: 100, height_mm: 100 }
    const wsW = ws.x_max - ws.x_min
    const wsH = ws.y_max - ws.y_min
    const w = Math.max(wsW * 0.6, 10)
    const h = Math.max(wsH * 0.6, 10)
    return { x_mm: (wsW - w) / 2, y_mm: (wsH - h) / 2, width_mm: w, height_mm: h }
  }

  function newVariantId(): string {
    return `v${Date.now().toString(36)}${Math.floor(Math.random() * 1000).toString(36)}`
  }

  function defaultVariant(): Variant {
    return {
      id: newVariantId(),
      name: i18n.global.t('variants.default'),
      layer_algorithms: {},
      visibility: {},
    }
  }

  function blankPlacement(): Placement {
    const size = defaultPlacementSize()
    const variant = defaultVariant()
    return {
      id: newPlacementId(),
      library_file_id: null,
      source_file: '',
      source_mime: '',
      job_id: null,
      rerenderable: false,
      svg: '',
      layers: [],
      source_bbox: emptyBbox(),
      layer_algorithms: {},
      upload_warnings: [],
      upload_metadata: {},
      last_file: null,
      last_options: undefined,
      visibility: {},
      variants: [variant],
      active_variant_id: variant.id,
      rotation: 0,
      flip_h: false,
      flip_v: false,
      ...size,
    }
  }

  function addEmptyPlacement(): string {
    const placement = blankPlacement()
    placements.value = [...placements.value, placement]
    selectedPlacementId.value = placement.id
    invalidateOutputs()
    return placement.id
  }

  // ====== Placement transforms (rotation / flip / centering) =============
  // These act on a placement's geometry without re-rendering the source
  // SVG: rotation is applied around the placement bbox centre, and a
  // quarter-turn swaps the bbox width / height so the workspace
  // footprint follows the rotated drawing. The transforms are baked into
  // the composite SVG sent to the backend so the gcode matches.
  function rotatePlacement(id: string, deltaDeg: number): void {
    const target = placements.value.find((p) => p.id === id)
    if (!target) return
    const next = (((target.rotation + deltaDeg) % 360) + 360) % 360
    // A quarter-turn swaps the on-plan footprint dimensions so the
    // drawing's outer bbox keeps matching the placement rect.
    const swap = Math.abs(deltaDeg) % 180 === 90
    const cx = target.x_mm + target.width_mm / 2
    const cy = target.y_mm + target.height_mm / 2
    const newW = swap ? target.height_mm : target.width_mm
    const newH = swap ? target.width_mm : target.height_mm
    patchPlacement(id, {
      rotation: next,
      width_mm: newW,
      height_mm: newH,
      x_mm: cx - newW / 2,
      y_mm: cy - newH / 2,
    })
  }

  function flipPlacement(id: string, axis: 'h' | 'v'): void {
    const target = placements.value.find((p) => p.id === id)
    if (!target) return
    if (axis === 'h') patchPlacement(id, { flip_h: !target.flip_h })
    else patchPlacement(id, { flip_v: !target.flip_v })
  }

  function duplicatePlacement(id: string, offsetMm = 15): string | null {
    const src = placements.value.find((p) => p.id === id)
    if (!src) return null
    // Variants are per-file — preserve their identities across clones so
    // edits made on one placement's active variant flow back through the
    // library snapshot to the other placements of the same file. Only
    // the per-placement geometry / live state is forked.
    const clonedVariants = src.variants.map((v) => ({
      ...v,
      layer_algorithms: { ...v.layer_algorithms },
      visibility: { ...v.visibility },
    }))
    const clone: Placement = {
      ...src,
      id: newPlacementId(),
      // ``library_file_id`` is intentionally preserved — both placements
      // draw from the same library entry.
      x_mm: src.x_mm + offsetMm,
      y_mm: src.y_mm + offsetMm,
      visibility: { ...src.visibility },
      layer_algorithms: { ...src.layer_algorithms },
      layers: src.layers.map((l) => ({ ...l })),
      variants: clonedVariants,
      active_variant_id: src.active_variant_id,
    }
    placements.value = [...placements.value, clone]
    invalidateOutputs()
    return clone.id
  }

  // ====== Backward-compat shims (read-only views into selected) ==========
  // These mirror the old single-job state so existing components keep
  // reading ``store.svg`` / ``store.layers`` / ``store.job`` without
  // knowing about placements. Mutations go through the helper functions
  // below, which act on ``selectedPlacement``.
  const job = computed<Job | null>(() => {
    const p = selectedPlacement.value
    if (!p || !p.source_file) return null
    return {
      job_id: p.job_id ?? '',
      source_file: p.source_file,
      source_mime: p.source_mime,
      profile_name: selectedProfileName.value,
      layers: p.layers,
      created_at: '',
      status: 'ready',
    }
  })
  const svg = computed<string | null>(() => selectedPlacement.value?.svg || null)
  const layers = computed<LayerInfo[]>(() => selectedPlacement.value?.layers ?? [])
  const lastFile = computed<File | null>(() => selectedPlacement.value?.last_file ?? null)
  const uploadWarnings = computed<string[]>(() => selectedPlacement.value?.upload_warnings ?? [])
  const uploadMetadata = computed<Record<string, unknown>>(
    () => selectedPlacement.value?.upload_metadata ?? {},
  )
  const layerAlgorithms = computed<Record<string, LayerAlgorithm>>(
    () => selectedPlacement.value?.layer_algorithms ?? {},
  )
  const visibility = computed<Record<string, boolean>>(
    () => selectedPlacement.value?.visibility ?? {},
  )

  interface DrawingRegion {
    x_mm: number
    y_mm: number
    width_mm: number
    height_mm: number
  }
  const currentDrawing = computed<DrawingRegion | null>(() => {
    const p = selectedPlacement.value
    if (!p || !p.source_file) return null
    return { x_mm: p.x_mm, y_mm: p.y_mm, width_mm: p.width_mm, height_mm: p.height_mm }
  })

  function setDrawing(patch: Partial<DrawingRegion>): void {
    const p = selectedPlacement.value
    if (!p) return
    patchSelected({
      x_mm: patch.x_mm ?? p.x_mm,
      y_mm: patch.y_mm ?? p.y_mm,
      width_mm: patch.width_mm ?? p.width_mm,
      height_mm: patch.height_mm ?? p.height_mm,
    })
  }

  function resetDrawing(): void {
    const p = selectedPlacement.value
    if (!p) return
    patchSelected(defaultPlacementSize())
  }

  // Restore a placement's natural proportions: derive the height from the
  // current width using the source bbox aspect ratio, so an operator who
  // free-stretched a drawing can snap it back to its true shape without
  // resetting position or overall size. A quarter-turn rotation
  // (``rotation % 180 !== 0``) swaps the bbox aspect so the on-plan
  // footprint stays consistent with the rotated content.
  function restorePlacementAspect(id: string): void {
    const target = placements.value.find((p) => p.id === id)
    if (!target) return
    const bw = target.source_bbox.x_max - target.source_bbox.x_min
    const bh = target.source_bbox.y_max - target.source_bbox.y_min
    if (bw <= 0 || bh <= 0) return
    const rotated = target.rotation % 180 !== 0
    const aspect = rotated ? bh / bw : bw / bh
    const cx = target.x_mm + target.width_mm / 2
    const cy = target.y_mm + target.height_mm / 2
    const newH = target.width_mm / aspect
    patchPlacement(id, {
      width_mm: target.width_mm,
      height_mm: newH,
      x_mm: cx - target.width_mm / 2,
      y_mm: cy - newH / 2,
    })
  }

  // ====== Misc state ====================================================
  const loading = ref(false)
  const error = ref<string | null>(null)
  const errorScope = ref<'upload' | 'optimize' | 'generate' | null>(null)

  const profiles = ref<MachineProfile[]>([])
  const selectedProfileName = ref('Custom CoreXY A3')

  const presets = ref<Preset[]>([])
  const selectedPresetName = ref<string>('')

  const optimizing = ref(false)
  const metrics = ref<ToolpathMetrics | null>(null)

  const generating = ref(false)
  const gcode = ref<string | null>(null)

  const preflighting = ref(false)
  const preflight = ref<PreflightReport | null>(null)

  // Single place that drops the cached pipeline outputs. Any edit that
  // changes what the backend would draw — geometry, layers, pen
  // assignments, visibility, the scene's placement set — invalidates the
  // toolpath metrics, the generated gcode and the preflight report so the
  // Simulator / G-code tabs never show a result that no longer matches the
  // operator's scene. Replaces the old ``deep: true`` watcher on
  // ``placements`` (which walked every SVG on every drag); explicit calls
  // from the mutators below are O(1) and don't traverse the placement tree.
  function invalidateOutputs(): void {
    metrics.value = null
    gcode.value = null
    preflight.value = null
  }

  const scaleMode = ref<'fit' | 'actual'>('fit')
  const marginMm = ref(10)
  const autoOptimize = ref(true)

  const selectedProfile = computed(
    () => profiles.value.find((p) => p.name === selectedProfileName.value) ?? null,
  )

  const isMultiColor = computed<boolean>(() => (selectedProfile.value?.pen_slot_count ?? 1) > 1)

  // ====== /rerender ======================================================
  let rerenderController: AbortController | null = null
  let rerenderTimer: ReturnType<typeof setTimeout> | null = null
  // Promise of the currently in-flight ``triggerRerender`` call. Used by
  // ``flushRerender`` so /preflight and /generate can wait for any
  // pending rerender to finish before consuming ``placement.svg`` —
  // closes the race window between switching a variant on the canvas
  // and immediately clicking Generate.
  let rerenderInFlight: Promise<void> | null = null

  function trackRerender(): void {
    const promise = triggerRerender().finally(() => {
      if (rerenderInFlight === promise) rerenderInFlight = null
    })
    rerenderInFlight = promise
  }

  // Drain any debounced + in-flight rerender so callers can safely read
  // ``placement.svg`` afterwards. Safe to call when nothing is pending.
  async function flushRerender(): Promise<void> {
    if (rerenderTimer) {
      clearTimeout(rerenderTimer)
      rerenderTimer = null
      trackRerender()
    }
    while (rerenderInFlight) {
      await rerenderInFlight
    }
  }

  // Per-layer overrides are applied via /rerender against the committed
  // placement SVG. The live /preview SVG (built from bitmap settings +
  // band_recipes only — it ignores layer_algorithms) has display priority
  // over placementSvg in EditPreviewPane, so an /rerender result alone
  // would be invisible to the operator as long as the preview is still
  // cached. Clearing the live preview SVG forces the pane to fall back
  // to placementSvg, which /rerender just updated. The next bitmap
  // tweak naturally re-runs /preview and re-installs a fresh preview
  // SVG, so this clear is one-shot per layer-override action.
  function clearLivePreviewSvg(): void {
    try {
      useEditState().previewSvg.value = ''
    } catch {
      // Pinia store accessed outside of a setup context — happens in
      // tests; safe to ignore since there's no UI to wash out.
    }
  }

  async function applyLayerAlgorithm(
    layerId: string,
    algorithm: string,
    algorithmOptions: Record<string, unknown> = {},
  ): Promise<void> {
    const p = selectedPlacement.value
    if (!p) return
    patchSelected({
      layer_algorithms: {
        ...p.layer_algorithms,
        [layerId]: { algorithm, algorithm_options: algorithmOptions },
      },
    })
    autoSyncActiveVariant()
    clearLivePreviewSvg()
    if (rerenderTimer) clearTimeout(rerenderTimer)
    rerenderTimer = setTimeout(trackRerender, 250)
  }

  /**
   * Apply the same ``algorithm`` + ``options`` to every layer of the
   * currently selected placement and trigger a single rerender. Used
   * by the v2 modal's "Generate" path: the policy resolver produces
   * one job-level recommendation, we propagate it across layers in
   * one shot rather than looping over ``applyLayerAlgorithm`` (each of
   * which would schedule its own debounced rerender).
   */
  /**
   * Render an arbitrary variant of a placement *without* mutating the
   * live placement state. Returns the freshly rendered SVG so callers
   * (e.g. the Compare drawer) can show two variants side by side.
   *
   * Uses the same ``/rerender`` endpoint as the live debounced path,
   * but never patches ``placement.svg`` — the cache stays consistent
   * with whichever variant is currently active.
   */
  async function renderVariant(
    placement: Placement,
    variant: Variant,
    signal?: AbortSignal,
  ): Promise<{ svg: string; warnings: string[] } | null> {
    if (!placement.job_id || !placement.rerenderable) return null
    const layersPayload = Object.entries(variant.layer_algorithms).map(([layer_id, spec]) => {
      if (spec.passes && spec.passes.length) {
        return {
          layer_id,
          passes: spec.passes.map((p) => ({
            algorithm: p.algorithm,
            algorithm_options: p.algorithm_options,
          })),
        }
      }
      return {
        layer_id,
        algorithm: spec.algorithm,
        algorithm_options: spec.algorithm_options,
      }
    })
    try {
      const result = await rerenderJob(placement.job_id, layersPayload, signal)
      return { svg: result.svg, warnings: result.warnings ?? [] }
    } catch (err) {
      if ((err as { name?: string }).name === 'CanceledError') return null
      throw err
    }
  }

  async function applyAlgorithmToAllLayers(
    algorithm: string,
    algorithmOptions: Record<string, unknown> = {},
  ): Promise<void> {
    const p = selectedPlacement.value
    if (!p) return
    const next: Record<string, LayerAlgorithm> = {}
    for (const layer of p.layers) {
      next[layer.layer_id] = {
        algorithm,
        algorithm_options: { ...algorithmOptions },
      }
    }
    patchSelected({ layer_algorithms: next })
    autoSyncActiveVariant()
    clearLivePreviewSvg()
    if (rerenderTimer) clearTimeout(rerenderTimer)
    rerenderTimer = setTimeout(trackRerender, 50)
  }

  async function clearLayerAlgorithm(layerId: string): Promise<void> {
    const p = selectedPlacement.value
    if (!p) return
    if (!(layerId in p.layer_algorithms)) return
    const next = { ...p.layer_algorithms }
    delete next[layerId]
    patchSelected({ layer_algorithms: next })
    autoSyncActiveVariant()
    clearLivePreviewSvg()
    if (rerenderTimer) clearTimeout(rerenderTimer)
    rerenderTimer = setTimeout(trackRerender, 250)
  }

  // Apply a multi-pass stack to one layer: ``passes`` is the ordered list
  // of algorithms (with options) drawn against the same colour mask. The
  // first pass plots first, the last on top — order is preserved in the
  // toolpath. An empty list clears the override (same as clearLayerAlgorithm).
  async function applyLayerPasses(layerId: string, passes: LayerPass[]): Promise<void> {
    const p = selectedPlacement.value
    if (!p) return
    if (!passes.length) {
      await clearLayerAlgorithm(layerId)
      return
    }
    // Mirror the first pass into the legacy algorithm/options fields so
    // existing UI that reads ``layer_algorithms[id].algorithm`` (e.g.
    // PrintStylePicker highlighting) still surfaces the dominant pass.
    const first = passes[0]!
    patchSelected({
      layer_algorithms: {
        ...p.layer_algorithms,
        [layerId]: {
          algorithm: first.algorithm,
          algorithm_options: { ...first.algorithm_options },
          passes: passes.map((pass) => ({
            algorithm: pass.algorithm,
            algorithm_options: { ...pass.algorithm_options },
          })),
        },
      },
    })
    autoSyncActiveVariant()
    clearLivePreviewSvg()
    if (rerenderTimer) clearTimeout(rerenderTimer)
    rerenderTimer = setTimeout(trackRerender, 250)
  }

  async function triggerRerender(): Promise<void> {
    const p = selectedPlacement.value
    if (!p || !p.job_id || !p.svg) return
    if (rerenderController) rerenderController.abort()
    const controller = new AbortController()
    rerenderController = controller
    // Per-rerender timing fuels the ``preview_refresh`` KPI in the
    // perf overlay (roadmap C.8). Aborted rerenders don't emit a
    // sample — the operator's intent was to cancel, not to observe.
    const perf = usePerfStore()
    const tStart = performance.now()
    try {
      const layersPayload = Object.entries(p.layer_algorithms).map(([layer_id, spec]) => {
        // Multi-pass stack: send ``passes`` so the backend stacks the
        // algorithms; the legacy single-algorithm fields stay populated
        // for back-compat but the backend prefers ``passes`` when set.
        if (spec.passes && spec.passes.length) {
          return {
            layer_id,
            passes: spec.passes.map((p) => ({
              algorithm: p.algorithm,
              algorithm_options: p.algorithm_options,
            })),
          }
        }
        return {
          layer_id,
          algorithm: spec.algorithm,
          algorithm_options: spec.algorithm_options,
        }
      })
      const result = await rerenderJob(p.job_id, layersPayload, controller.signal)
      if (controller.signal.aborted) return
      // patchPlacement already invalidates the cached outputs for the new SVG.
      patchPlacement(p.id, { svg: result.svg })
    } catch (err) {
      if (controller.signal.aborted) return
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 404) {
        // Cache evicted (backend restart, LRU rollover). Surface a soft
        // hint so the operator knows their tweak didn't render — the
        // previous silent path left them wondering why the canvas
        // didn't update. Re-uploading via the Apply button rebuilds
        // the segmentation cache; the hint includes that affordance.
        const toasts = useToastStore()
        toasts.info(i18n.global.t('layers.rerenderCacheMiss'), 4000)
      } else if (status === 405) {
        const toasts = useToastStore()
        toasts.warning(i18n.global.t('layers.rerenderUnavailable'))
      } else {
        const toasts = useToastStore()
        toasts.warning((err as Error).message || i18n.global.t('layers.rerenderFailed'))
      }
    } finally {
      if (rerenderController === controller) rerenderController = null
      if (!controller.signal.aborted) {
        perf.recordTiming('preview_refresh', performance.now() - tStart, p.id)
      }
    }
  }

  // ====== Per-layer utilities (act on selected) ==========================
  const missingPenSlots = computed<number[]>(() => {
    const profile = selectedProfile.value
    if (!profile) return []
    const hasExplicit = (profile.pens?.length ?? 0) > 0
    const installed = new Set((profile.pens ?? []).filter((p) => p.installed).map((p) => p.index))
    const missing = new Set<number>()
    // Only the placements actually on the plan gate generation — drafts
    // would raise spurious "install a pen" warnings for a file the
    // operator hasn't added yet.
    for (const placement of visiblePlacements.value) {
      for (const layer of placement.layers) {
        const slot = layer.target_pen_slot
        if (slot === null) continue
        if (slot < 0 || slot >= profile.pen_slot_count) missing.add(slot)
        else if (hasExplicit && !installed.has(slot)) missing.add(slot)
      }
    }
    return [...missing].sort((a, b) => a - b)
  })

  function effectiveSpeed(layer: LayerInfo): number {
    return (
      layer.drawing_speed_mm_s ?? selectedProfile.value?.drawing_speed_mm_s ?? DEFAULT_SPEED_MM_S
    )
  }

  function layerDurationSeconds(layer: LayerInfo): number {
    const speed = effectiveSpeed(layer)
    return speed > 0 ? layer.total_length_mm / speed : 0
  }

  const totalLengthMm = computed(() =>
    visiblePlacements.value.reduce(
      (sum, p) => sum + p.layers.reduce((s, l) => s + l.total_length_mm, 0),
      0,
    ),
  )

  const totalDurationSeconds = computed(() =>
    visiblePlacements.value.reduce(
      (sum, p) => sum + p.layers.reduce((s, l) => s + layerDurationSeconds(l), 0),
      0,
    ),
  )

  function setVisibility(layerId: string, visible: boolean): void {
    const p = selectedPlacement.value
    if (!p) return
    patchSelected({ visibility: { ...p.visibility, [layerId]: visible } })
    autoSyncActiveVariant()
  }
  function isVisible(layerId: string): boolean {
    return visibility.value[layerId] ?? true
  }

  function updateLayer(layerId: string, patch: Partial<LayerInfo>): void {
    const p = selectedPlacement.value
    if (!p) return
    patchSelected({
      layers: p.layers.map((layer) =>
        layer.layer_id === layerId ? { ...layer, ...patch } : layer,
      ),
    })
  }

  function reorderLayers(ordered: LayerInfo[]): void {
    patchSelected({ layers: ordered.map((layer, index) => ({ ...layer, draw_order: index })) })
  }

  // Resolve the palette pool the editor is currently pointed at: the
  // operator's palette-source choice (pens / available / union) applied to
  // the selected profile's installed pens and the available-colours
  // inventory. Mirrors ``resolveEffectivePalette`` so the re-snap below
  // lands on exactly the swatches the per-layer picker offers.
  function currentEffectivePalette(): string[] {
    const source = usePaletteSourceStore().source
    const pens = (selectedProfile.value?.pens ?? [])
      .filter((p) => p.installed && p.color)
      .map((p) => p.color)
    const available = useAvailableColorsStore().ordered.map((c) => c.hex)
    return resolveEffectivePalette(source, pens, available)
  }

  // Re-snap every ``auto`` layer (across ALL placements) to the nearest hex
  // in the active pool, preserving ``manual`` overrides. Called when the
  // operator changes the palette source or swaps the installed pens so the
  // assigned colours follow the pool they just selected — without this the
  // colours stayed pinned to whatever the profile-agnostic upload picked.
  // An empty pool clears the auto value (assigned_color_hex = null), which
  // matches the backend's fallback to the raw centroid.
  function resnapAutoLayers(poolOverride?: readonly string[]): void {
    const pool = poolOverride ?? currentEffectivePalette()
    let changed = false
    placements.value = placements.value.map((p) => {
      let touched = false
      const layers = p.layers.map((layer) => {
        if (layer.color_assignment === 'manual') return layer
        const next = pool.length ? nearestPoolHex(layer.source_color, pool) : null
        if ((layer.assigned_color_hex ?? null) === (next ?? null)) return layer
        touched = true
        return { ...layer, assigned_color_hex: next, color_assignment: 'auto' as const }
      })
      if (!touched) return p
      changed = true
      return { ...p, layers }
    })
    if (changed) invalidateOutputs()
  }

  watch([scaleMode, marginMm, selectedProfileName], invalidateOutputs)

  // Re-snap auto layers whenever the active pool changes — the operator
  // toggled the palette source (pens / available / union), edited the
  // available-colours inventory, or swapped the installed pens. Keying the
  // watcher on the serialised palette means a no-op change (same swatches)
  // doesn't churn; ``resnapAutoLayers`` itself only patches layers that
  // actually move, so manual overrides and unchanged autos stay put.
  watch(
    () => currentEffectivePalette().join('|'),
    () => resnapAutoLayers(),
  )
  async function loadProfiles(): Promise<void> {
    profiles.value = await getProfiles()
    if (!selectedProfile.value && profiles.value.length) {
      selectedProfileName.value = profiles.value[0]!.name
    }
  }

  async function loadPresets(): Promise<void> {
    presets.value = await getPresets()
  }

  async function saveProfile(profile: MachineProfile): Promise<void> {
    const saved = await apiSaveProfile(profile)
    await loadProfiles()
    selectedProfileName.value = saved.name
  }

  async function deleteProfile(name: string): Promise<void> {
    await apiDeleteProfile(name)
    await loadProfiles()
    if (selectedProfileName.value === name && profiles.value.length) {
      selectedProfileName.value = profiles.value[0]!.name
    }
  }

  // ====== Upload ========================================================
  // Upload routes through the library store: the file is stored on the
  // backend (deduplicated by SHA-256) and the selected placement is then
  // populated from the library entry. If no placement exists yet, a fresh
  // one is created so the rest of the editor has something to act on.
  //
  // Reactive AbortController for the in-flight POST. Exposed so the
  // progress toast's Cancel button can fire ``abort()`` without keeping
  // a closure-captured reference around — and so a second upload click
  // bails before clobbering the placement.
  let uploadController: AbortController | null = null

  async function upload(file: File, optionsOverride?: Record<string, unknown>): Promise<void> {
    // Single-flight guard: a duplicate click while a POST is already
    // in-flight would race with patchPlacement and could end up with
    // ``last_file`` pointing at one bytes blob and the resulting SVG
    // coming from the other.
    if (loading.value) return
    // Client-side validation (size, empty, extension). Surfaces the
    // same error the backend would have returned, but without paying
    // the upload cost — particularly important for large files.
    const validation = validateUploadFile(file)
    if (validation) {
      const toasts = useToastStore()
      toasts.error(validation.message)
      error.value = validation.message
      errorScope.value = 'upload'
      return
    }
    const preset = presets.value.find((p) => p.name === selectedPresetName.value)
    const options =
      preset?.options || optionsOverride ? { ...preset?.options, ...optionsOverride } : undefined
    if (!selectedPlacement.value) {
      addEmptyPlacement()
    }
    const targetId = selectedPlacementId.value!
    loading.value = true
    error.value = null
    errorScope.value = null
    patchPlacement(targetId, {
      upload_warnings: [],
      upload_metadata: {},
      layer_algorithms: {},
      last_file: file,
      last_options: options,
    })
    // patchPlacement above already invalidated the cached outputs.
    const toasts = useToastStore()
    const library = useLibraryStore()
    uploadController = new AbortController()
    const controller = uploadController
    // Show the initial "Uploading <name> (0%)" toast with an inline
    // Cancel action. Once the body is fully transmitted, the message
    // switches to "Converting on server…" — the operator sees the
    // transition from network upload to server-side work, instead of
    // a single opaque spinner.
    const toastId = toasts.progress(
      i18n.global.t('toast.uploadingPercent', { name: file.name, percent: 0 }),
      {
        label: i18n.global.t('upload.cancel'),
        onClick: () => controller.abort(),
      },
    )
    try {
      const result = await library.upload(file, {
        convertOptions: options,
        signal: controller.signal,
        silent: true,
        onProgress: (percent: number) => {
          if (controller.signal.aborted) return
          const message =
            percent >= 100
              ? i18n.global.t('toast.convertingOnServer', { name: file.name })
              : i18n.global.t('toast.uploadingPercent', { name: file.name, percent })
          toasts.update(toastId, 'progress', message, 0)
        },
      })
      if (!result) {
        if (controller.signal.aborted) {
          // Operator cancelled — turn the progress toast into a brief
          // info note so they see the action took effect.
          toasts.update(toastId, 'info', i18n.global.t('toast.uploadCancelled'), 3000)
        } else {
          // library.upload swallowed the error silently; show the
          // generic upload-failed message on the same toast.
          toasts.update(toastId, 'error', i18n.global.t('upload.failed'), 6000)
        }
        patchPlacement(targetId, { svg: '', layers: [] })
        error.value = controller.signal.aborted ? null : i18n.global.t('upload.failed')
        errorScope.value = controller.signal.aborted ? null : 'upload'
        return
      }
      const detail = result.file
      const bboxes = detail.layers.map((l) => l.bbox)
      const sourceBbox = unionBoxes(bboxes) ?? emptyBbox()
      const layoutPatch = computeInitialLayout(
        sourceBbox,
        targetId,
        intrinsicPageSize(detail.upload_metadata),
      )
      patchPlacement(targetId, {
        library_file_id: detail.file_id,
        source_file: detail.source_file,
        source_mime: detail.source_mime,
        // ``file_id`` doubles as the cache key for /rerender (see api/files.py).
        job_id: detail.file_id,
        rerenderable: detail.rerenderable ?? false,
        svg: detail.svg,
        layers: detail.layers.map((layer) =>
          autoOptimize.value ? { ...layer, optimize: true } : layer,
        ),
        source_bbox: sourceBbox,
        upload_warnings: detail.warnings ?? [],
        upload_metadata: detail.upload_metadata ?? {},
        visibility: Object.fromEntries(detail.layers.map((l) => [l.layer_id, true])),
        ...layoutPatch,
      })
      // The library upload snaps colours profile-agnostically (see
      // api/files.py). Re-snap the fresh auto layers against the active
      // pool now so the assigned colours reflect the operator's installed
      // pens / palette-source choice immediately — not just after a later
      // source toggle.
      resnapAutoLayers()
      // Persist the config this conversion was applied with to the
      // library so the next "Edit from library" reopens with the same
      // segmentation / master style / preprocess. (Layer-level mutations
      // sync on their own; a plain re-convert with no per-layer overrides
      // wouldn't otherwise reach the library.)
      syncPlacementToLibrary(placements.value.find((p) => p.id === targetId) ?? null)
      toasts.update(
        toastId,
        'success',
        i18n.global.t('toast.uploaded', {
          name: detail.source_file,
          count: detail.layers.length,
        }),
        4000,
      )
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('upload.failed'))
      error.value = message
      errorScope.value = 'upload'
      // Reset svg/layers on the target placement so the UI shows the
      // drop-zone again instead of stale content.
      patchPlacement(targetId, { svg: '', layers: [] })
      toasts.update(toastId, 'error', message, 6000)
    } finally {
      loading.value = false
      if (uploadController === controller) uploadController = null
    }
  }

  // Imperative cancel hook for callers (e.g. modal close, navigation
  // guard) that need to abort an in-flight upload without going through
  // the toast button.
  function cancelUpload(): void {
    uploadController?.abort()
  }

  // Create a new placement on the plan from an existing library entry.
  // ``position`` (workspace mm) centres the placement on that point; when
  // omitted, the placement is centred on the workspace.
  // ``asDraft=true`` creates a hidden working copy for "Edit from library"
  // — the placement holds the operator's conversion-settings draft but
  // doesn't appear on the sheet until ``materializeLibraryDraft`` is
  // called (typically from the "Add to plan" button in the modal footer).
  async function createPlacementFromLibrary(
    fileId: string,
    position?: { x: number; y: number },
    options: { asDraft?: boolean } = {},
  ): Promise<string | null> {
    const library = useLibraryStore()
    const detail = await library.ensureDetail(fileId)
    if (!detail) return null
    const placement = blankPlacement()
    if (options.asDraft) placement.is_library_draft = true
    const bboxes = detail.layers.map((l) => l.bbox)
    const sourceBbox = unionBoxes(bboxes) ?? emptyBbox()
    placements.value = [...placements.value, placement]
    selectedPlacementId.value = placement.id
    const layoutPatch = computeInitialLayout(
      sourceBbox,
      placement.id,
      intrinsicPageSize(detail.upload_metadata),
    )
    // If this library entry has previously-saved variants, hydrate them
    // onto the new placement so the file renders with its last-used print
    // settings instead of the default conversion. Otherwise fall back to
    // a fresh default variant generated by ``blankPlacement``.
    const saved = library.getFileVariants(detail.file_id)
    const variantPatch: Partial<Placement> = {}
    let activeVariantForRerender: Variant | null = null
    if (saved && saved.variants.length) {
      const activeId =
        saved.variants.find((v) => v.id === saved.active_variant_id)?.id ?? saved.variants[0]!.id
      const active = saved.variants.find((v) => v.id === activeId)!
      activeVariantForRerender = active
      variantPatch.variants = saved.variants
      variantPatch.active_variant_id = activeId
      variantPatch.layer_algorithms = { ...active.layer_algorithms }
    }
    // Restore the saved editor config so the modal opens showing the
    // chosen segmentation / master style / preprocess the operator last
    // applied to this file, instead of resetting the draft to defaults.
    // ``rehydrateDraft`` reads ``placement.last_options`` directly.
    if (saved?.last_options) {
      variantPatch.last_options = { ...saved.last_options }
    }
    patchPlacement(placement.id, {
      library_file_id: detail.file_id,
      source_file: detail.source_file,
      source_mime: detail.source_mime,
      job_id: detail.file_id,
      rerenderable: detail.rerenderable ?? false,
      svg: detail.svg,
      layers: detail.layers.map((layer) =>
        autoOptimize.value ? { ...layer, optimize: true } : layer,
      ),
      source_bbox: sourceBbox,
      upload_warnings: detail.warnings ?? [],
      upload_metadata: detail.upload_metadata ?? {},
      // Merge saved per-layer visibility on top of the default-all-visible
      // map so layers the operator had hidden in their variant stay hidden.
      visibility: {
        ...Object.fromEntries(detail.layers.map((l) => [l.layer_id, true])),
        ...(activeVariantForRerender?.visibility ?? {}),
      },
      ...layoutPatch,
      ...variantPatch,
    })
    if (position) {
      const ws = selectedProfile.value?.workspace
      const fresh = placements.value.find((p) => p.id === placement.id)
      if (ws && fresh) {
        patchPlacement(placement.id, {
          x_mm: Math.max(0, position.x - fresh.width_mm / 2 - ws.x_min),
          y_mm: Math.max(0, position.y - fresh.height_mm / 2 - ws.y_min),
        })
      }
    }
    // Snap the freshly-hydrated auto layers against the active pool so a
    // library placement reflects the operator's installed pens / palette
    // source, not just the profile-agnostic snap baked in at upload.
    resnapAutoLayers()
    // Kick a /rerender so the canvas shows the file with the hydrated
    // settings rather than the default conversion that came back from
    // the library detail endpoint.
    if (activeVariantForRerender && Object.keys(activeVariantForRerender.layer_algorithms).length) {
      if (rerenderTimer) clearTimeout(rerenderTimer)
      rerenderTimer = setTimeout(trackRerender, 50)
    }
    return placement.id
  }

  function computeInitialLayout(
    sourceBbox: BoundingBox,
    placementId: string,
    intrinsicSize?: { width_mm: number; height_mm: number } | null,
  ): Partial<Placement> {
    const profile = selectedProfile.value
    if (!profile) return {}
    const ws = profile.workspace
    const wsW = ws.x_max - ws.x_min
    const wsH = ws.y_max - ws.y_min
    const usableW = Math.max(wsW - 2 * marginMm.value, wsW * 0.5)
    const usableH = Math.max(wsH - 2 * marginMm.value, wsH * 0.5)
    let width: number
    let height: number
    if (intrinsicSize && intrinsicSize.width_mm > 0 && intrinsicSize.height_mm > 0) {
      // PDF / DOCX / HTML: the converter reports the source page
      // dimensions in mm so an A4 doc lands at 210×297 mm on the
      // workspace instead of being scaled to whatever fraction of the
      // workspace the drawn content happened to cover. Clamp down (but
      // never up) if the page is larger than the usable area.
      const fit = Math.min(1, usableW / intrinsicSize.width_mm, usableH / intrinsicSize.height_mm)
      width = intrinsicSize.width_mm * fit
      height = intrinsicSize.height_mm * fit
    } else {
      const bboxW = Math.max(sourceBbox.x_max - sourceBbox.x_min, 1e-6)
      const bboxH = Math.max(sourceBbox.y_max - sourceBbox.y_min, 1e-6)
      const scale = Math.min(usableW / bboxW, usableH / bboxH)
      width = bboxW * scale
      height = bboxH * scale
    }
    // Preserve existing x/y if the placement already had real content;
    // otherwise centre. We detect "fresh" by checking source_file empty
    // before this upload mutated it — but at this point we've already
    // overwritten metadata, so use width_mm check on the prior state.
    const prior = placements.value.find((p) => p.id === placementId)
    const wasFresh = !prior?.source_file
    if (wasFresh) {
      return {
        x_mm: (wsW - width) / 2,
        y_mm: (wsH - height) / 2,
        width_mm: width,
        height_mm: height,
      }
    }
    return { width_mm: width, height_mm: height }
  }

  // Pulls the optional native page dimensions out of an upload-metadata
  // bag. PDF / DOCX / HTML converters report ``page_width_mm`` and
  // ``page_height_mm``; other formats omit them, in which case the
  // caller falls back to scaling the content bbox to fit.
  function intrinsicPageSize(
    metadata: Record<string, unknown> | undefined,
  ): { width_mm: number; height_mm: number } | null {
    const w = Number(metadata?.page_width_mm)
    const h = Number(metadata?.page_height_mm)
    if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) {
      return null
    }
    return { width_mm: w, height_mm: h }
  }

  function clearJob(): void {
    placements.value = []
    selectedPlacementId.value = null
    invalidateOutputs()
    error.value = null
    errorScope.value = null
  }

  // Re-converts the SELECTED placement's source file with a new ``page``
  // option. Uses the legacy /upload path directly so we don't add a second
  // library entry every time the operator flips pages on a multi-page PDF;
  // the library entry that backs this placement keeps the originally
  // uploaded bytes, only the rendered SVG / layers change here.
  async function changePage(page: number): Promise<void> {
    const p = selectedPlacement.value
    if (!p) return
    // ``last_file`` is only populated in-memory after a fresh /upload
    // round-trip. Library drag-drop placements and post-reload sessions
    // arrive with ``last_file: null`` but a valid ``library_file_id`` —
    // re-fetch the original bytes from disk so page navigation still
    // works in those cases.
    let file = p.last_file
    if (!file && p.library_file_id && p.source_file) {
      try {
        file = await downloadOriginalFile(
          p.library_file_id,
          p.source_file,
          p.source_mime || 'application/octet-stream',
        )
        patchPlacement(p.id, { last_file: file })
      } catch {
        return
      }
    }
    if (!file) return
    const targetId = p.id
    const next = { ...(p.last_options ?? {}), page }
    loading.value = true
    error.value = null
    errorScope.value = null
    patchPlacement(targetId, { last_options: next })
    const toasts = useToastStore()
    const toastId = toasts.progress(i18n.global.t('toast.converting'))
    try {
      const result = await uploadFile(file, selectedProfileName.value, next)
      const bboxes = result.job.layers.map((l) => l.bbox)
      const sourceBbox = unionBoxes(bboxes) ?? emptyBbox()
      // Force-resize to the new page's native dimensions: each PDF page
      // may have its own size (a brochure can mix A4 inserts with an A3
      // cover) and the operator explicitly asked for "if page A4 then
      // prepare A4" — so we override ``wasFresh`` and always emit
      // ``x_mm`` / ``y_mm`` recentred on the new page.
      const intrinsic = intrinsicPageSize(result.metadata)
      const layoutPatch = computeInitialLayout(sourceBbox, targetId, intrinsic)
      const profile = selectedProfile.value
      if (intrinsic && profile) {
        const ws = profile.workspace
        const wsW = ws.x_max - ws.x_min
        const wsH = ws.y_max - ws.y_min
        const w = layoutPatch.width_mm ?? intrinsic.width_mm
        const h = layoutPatch.height_mm ?? intrinsic.height_mm
        layoutPatch.x_mm = Math.max(0, (wsW - w) / 2)
        layoutPatch.y_mm = Math.max(0, (wsH - h) / 2)
      }
      patchPlacement(targetId, {
        source_file: result.job.source_file,
        source_mime: result.job.source_mime,
        job_id: result.job.job_id,
        svg: result.svg,
        layers: result.job.layers.map((layer) =>
          autoOptimize.value ? { ...layer, optimize: true } : layer,
        ),
        source_bbox: sourceBbox,
        upload_warnings: result.warnings ?? [],
        upload_metadata: result.metadata ?? {},
        visibility: Object.fromEntries(result.job.layers.map((l) => [l.layer_id, true])),
        ...layoutPatch,
      })
      toasts.update(toastId, 'success', i18n.global.t('toast.converted'), 3000)
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('upload.failed'))
      error.value = message
      errorScope.value = 'upload'
      toasts.update(toastId, 'error', message, 6000)
    } finally {
      loading.value = false
    }
  }

  // ====== Optimize / Preflight / Generate (composite) ====================
  // Optimize still operates on a single placement (only the selected one),
  // since the optimizer is local to a drawing. Preflight + generate fold
  // ALL placements into one composite SVG sent to the backend.
  async function optimize(): Promise<void> {
    const p = selectedPlacement.value
    if (!p?.svg) return
    optimizing.value = true
    error.value = null
    errorScope.value = null
    const toasts = useToastStore()
    const toastId = toasts.progress(i18n.global.t('toast.optimizing'))
    try {
      const result = await optimizeToolpaths(
        p.svg,
        p.layers.map((layer) => ({
          layer_id: layer.layer_id,
          optimize: layer.optimize,
          simplify_tolerance_mm: layer.simplify_tolerance_mm,
        })),
      )
      patchPlacement(p.id, {
        svg: result.svg,
        layers: result.layers,
        visibility: Object.fromEntries(result.layers.map((l) => [l.layer_id, true])),
      })
      metrics.value = result.metrics
      gcode.value = null
      preflight.value = null
      toasts.update(toastId, 'success', i18n.global.t('toast.optimized'), 3000)
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('layers.optimizeFailed'))
      error.value = message
      errorScope.value = 'optimize'
      toasts.update(toastId, 'error', message, 6000)
    } finally {
      optimizing.value = false
    }
  }

  // Build the ``PrintPlan`` sent to ``/preflight`` and ``/generate``.
  //
  // This is the only place that projects placements + layer settings
  // into the backend's wire format — every consumer goes through it,
  // so adding a new layer field means editing exactly one mapping
  // (``toLayerPlan`` in ``domain/plan-builder.ts``) and the OpenAPI
  // types catch anything that drifted.
  function buildPlanPayload(): PrintPlan | null {
    const profile = selectedProfile.value
    if (!profile) return null
    // Exclude "Edit from library" drafts: they hold conversion settings but
    // aren't on the plan (see visiblePlacements), so they must never reach
    // the composite / generated G-code.
    const ready = placements.value.filter((p) => !p.is_library_draft && p.svg && p.layers.length)
    if (!ready.length) return null
    const result = buildComposite(ready, profile)
    // The backend ``_make_transform`` centres the drawing on the
    // drawable region. To preserve the absolute workspace coordinates
    // we baked into the composite, define the region to be exactly the
    // union of the rendered layer bboxes — region_center then matches
    // bbox_center and the transform collapses to identity.
    const bbox = unionBoxes(result.layers.map((l) => l.bbox))
    let placement: PrintPlan['placement'] = null
    if (bbox) {
      const ws = profile.workspace
      placement = {
        offset_x_mm: Math.max(0, bbox.x_min - ws.x_min),
        offset_y_mm: Math.max(0, bbox.y_min - ws.y_min),
        sheet_width_mm: Math.max(1e-3, bbox.x_max - bbox.x_min),
        sheet_height_mm: Math.max(1e-3, bbox.y_max - bbox.y_min),
      }
    }
    // Forward the currently-edited typography draft into the plan
    // when the (first) ready placement is a text source. The hash +
    // persisted snapshot then reflect the font / size / weight the
    // operator chose, closing the regression class where typo edits
    // silently never reached the pivot. Pair with the placement's
    // ``library_file_id`` + ``source_mime`` so the backend's
    // in-pipeline text rerender (post-L5) can re-render straight from
    // the library bytes — no re-upload needed when the operator
    // tweaks the font. See ``buildTypographyPlan`` for the
    // single-draft limitation acknowledged in this iteration.
    const textPlacement = ready.find((p) => p.source_mime)
    const typography = buildTypographyPlan(textPlacement?.source_mime)
    return buildPrintPlan({
      svg: result.svg,
      profileName: selectedProfileName.value,
      layers: result.layers,
      placement,
      typography,
      libraryFileId: textPlacement?.library_file_id ?? null,
      sourceMime: textPlacement?.source_mime ?? null,
    })
  }

  async function runPreflight(): Promise<void> {
    // Wait for any pending /rerender to land first — otherwise we'd
    // preflight against the previous variant's SVG.
    await flushRerender()
    const plan = buildPlanPayload()
    if (!plan) return
    preflighting.value = true
    error.value = null
    errorScope.value = null
    const toasts = useToastStore()
    const toastId = toasts.progress(i18n.global.t('toast.preflighting'))
    try {
      preflight.value = await preflightCheck(plan)
      toasts.update(toastId, 'success', i18n.global.t('toast.preflightOk'), 3000)
    } catch (err) {
      preflight.value = null
      const message = errorDetail(err, i18n.global.t('preflight.failed'))
      error.value = message
      errorScope.value = 'generate'
      toasts.update(toastId, 'error', message, 6000)
    } finally {
      preflighting.value = false
    }
  }

  async function generate(): Promise<void> {
    // Wait for any pending /rerender to land first — otherwise the
    // composite would bake in the previous variant's SVG, and the
    // operator would be confused why their just-picked print style
    // didn't make it into the toolpath.
    await flushRerender()

    const ready = placements.value.some((p) => p.svg && p.layers.length)
    if (!ready) return

    generating.value = true
    optimizing.value = true
    error.value = null
    errorScope.value = null
    metrics.value = null
    preflight.value = null
    gcode.value = null

    // Single AbortController drives every step so the modal's Cancel
    // button stops whatever is in flight. The pipeline use-case
    // receives the signal and threads it through every API call.
    const ui = useUiStore()
    const controller = new AbortController()
    ui.startGcodeJob('optimize', i18n.global.t('gcodeJob.optimizing'), () => controller.abort())

    let phase: 'optimize' | 'preflight' | 'generate' = 'optimize'
    try {
      const outcome = await runGeneratePipeline({
        // Drafts are excluded from the plan (buildPlanPayload), so there's
        // no point optimising them either — keep the two paths in lock-step.
        placements: placements.value
          .filter((p) => !p.is_library_draft)
          .map((p) => ({
            id: p.id,
            svg: p.svg,
            layers: p.layers,
          })),
        applyOptimized: (id, result) => {
          patchPlacement(id, {
            svg: result.svg,
            layers: result.layers,
            visibility: Object.fromEntries(result.layers.map((l) => [l.layer_id, true])),
          })
        },
        buildPlan: buildPlanPayload,
        onPhase: (next) => {
          phase = next
          if (next === 'optimize') {
            // already started above
          } else if (next === 'preflight') {
            optimizing.value = false
            preflighting.value = true
            ui.updateGcodeJobStep('preflight', i18n.global.t('gcodeJob.preflighting'))
          } else {
            preflighting.value = false
            ui.updateGcodeJobStep('generate', i18n.global.t('gcodeJob.generating'))
          }
        },
        onMetrics: (m) => {
          if (m) metrics.value = m
        },
        confirmMissingPenSlots: async (detail) => {
          // 409 from /generate. Surface a blocking dialog with the
          // specific slot list so the operator decides knowingly.
          // Confirming retries the call with allow_missing_slots=true.
          return await confirmAction({
            title: i18n.global.t('generate.missingSlots.title'),
            message: i18n.global.t('generate.missingSlots.message', {
              slots: detail.slots.join(', '),
            }),
            confirmLabel: i18n.global.t('generate.missingSlots.confirm'),
            cancelLabel: i18n.global.t('generate.missingSlots.cancel'),
            danger: true,
          })
        },
        signal: controller.signal,
      })
      preflight.value = outcome.preflight
      gcode.value = outcome.gcode
      ui.finishGcodeJob('success', i18n.global.t('gcodeJob.success'))
      // Auto-dismiss the success state after a short pause so the modal
      // doesn't linger — the operator can already see the generated
      // G-code / simulator tab update behind it.
      setTimeout(() => {
        if (ui.gcodeJobState.phase === 'success') ui.dismissGcodeJob()
      }, 1500)
    } catch (err) {
      const aborted =
        controller.signal.aborted ||
        err instanceof PipelineAbortedError ||
        (err instanceof DOMException && err.name === 'AbortError') ||
        (err as { code?: string })?.code === 'ERR_CANCELED'
      if (aborted) {
        ui.finishGcodeJob('cancelled', i18n.global.t('gcodeJob.cancelled'))
      } else {
        const message = pipelineErrorMessage(phase, err)
        error.value = message
        errorScope.value = phase === 'optimize' ? 'optimize' : 'generate'
        ui.finishGcodeJob('error', message, message)
      }
    } finally {
      generating.value = false
      optimizing.value = false
      preflighting.value = false
    }
  }

  // ====== Scene persistence =============================================
  // Placements (sans the un-serializable ``last_file`` File handle), the
  // current selection, profile, scale settings and auto-optimize toggle
  // are written to ``localStorage`` on a debounce so a tab refresh keeps
  // the scene intact. SVGs can be large — if quota is hit we fail
  // silently and the user simply doesn't get persistence that session.
  // ====== Variants (named snapshots of layer choices on a placement) ====
  const activeVariant = computed<Variant | null>(() => {
    const p = selectedPlacement.value
    if (!p) return null
    return p.variants.find((v) => v.id === p.active_variant_id) ?? p.variants[0] ?? null
  })

  // Roll the placement's live layer_algorithms + visibility into the
  // active variant snapshot, then mirror the whole variants list back to
  // the library so the file remembers its settings. Called from the
  // layer-algorithm / visibility mutators so the file-level snapshot is
  // always current — operators no longer have to click "Update".
  function autoSyncActiveVariant(): void {
    const p = selectedPlacement.value
    if (!p) return
    const next = p.variants.map((v) =>
      v.id === p.active_variant_id
        ? { ...v, layer_algorithms: { ...p.layer_algorithms }, visibility: { ...p.visibility } }
        : v,
    )
    patchSelected({ variants: next })
    syncPlacementToLibrary(selectedPlacement.value)
  }

  // Snapshot the placement's current live state (layer_algorithms +
  // visibility) into a new variant. Returns the new variant id, or
  // null if no placement is selected.
  function addVariant(name: string): string | null {
    const p = selectedPlacement.value
    if (!p) return null
    const variant: Variant = {
      id: newVariantId(),
      name: name.trim() || i18n.global.t('variants.untitled'),
      layer_algorithms: { ...p.layer_algorithms },
      visibility: { ...p.visibility },
    }
    patchSelected({
      variants: [...p.variants, variant],
      active_variant_id: variant.id,
    })
    syncSelectedToLibrary()
    return variant.id
  }

  // Overwrite the active variant with the placement's current live state.
  function updateActiveVariant(): void {
    const p = selectedPlacement.value
    if (!p) return
    const next = p.variants.map((v) =>
      v.id === p.active_variant_id
        ? { ...v, layer_algorithms: { ...p.layer_algorithms }, visibility: { ...p.visibility } }
        : v,
    )
    patchSelected({ variants: next })
    syncSelectedToLibrary()
  }

  function renameVariant(variantId: string, name: string): void {
    const p = selectedPlacement.value
    if (!p) return
    const trimmed = name.trim() || i18n.global.t('variants.untitled')
    patchSelected({
      variants: p.variants.map((v) => (v.id === variantId ? { ...v, name: trimmed } : v)),
    })
    syncSelectedToLibrary()
  }

  function removeVariant(variantId: string): void {
    const p = selectedPlacement.value
    if (!p) return
    // Never delete the last variant — keep at least one so the placement
    // always has a tracked snapshot to roll back to.
    if (p.variants.length <= 1) return
    const next = p.variants.filter((v) => v.id !== variantId)
    const wasActive = p.active_variant_id === variantId
    const newActive = wasActive ? (next[0]?.id ?? '') : p.active_variant_id
    patchSelected({ variants: next, active_variant_id: newActive })
    // Loading the new active variant restores its snapshot into live
    // state. Look up by id (not next[0]) so the load matches newActive
    // even when the deleted variant wasn't at index 0.
    if (wasActive) loadVariantState(next.find((v) => v.id === newActive))
    syncSelectedToLibrary()
  }

  // Load a variant's snapshot into the placement's live state and
  // trigger a /rerender so the canvas reflects the swap.
  function loadVariantState(variant: Variant | undefined): void {
    if (!variant) return
    patchSelected({
      layer_algorithms: { ...variant.layer_algorithms },
      visibility: { ...variant.visibility },
    })
    if (rerenderTimer) clearTimeout(rerenderTimer)
    rerenderTimer = setTimeout(trackRerender, 50)
  }

  function setActiveVariant(variantId: string): void {
    const p = selectedPlacement.value
    if (!p) return
    const target = p.variants.find((v) => v.id === variantId)
    if (!target) return
    patchSelected({ active_variant_id: variantId })
    loadVariantState(target)
    syncSelectedToLibrary()
  }

  // Set the active variant on an arbitrary placement (not necessarily the
  // currently-selected one). Used by the per-placement variant picker
  // shown on the plan when a placement has more than one variant.
  function setPlacementActiveVariant(placementId: string, variantId: string): void {
    const target = placements.value.find((p) => p.id === placementId)
    if (!target) return
    if (!target.variants.find((v) => v.id === variantId)) return
    selectedPlacementId.value = placementId
    setActiveVariant(variantId)
  }

  // Hydrate from localStorage and auto-persist on changes. The full
  // (de)serialisation + legacy-key migration logic lives in
  // ``infrastructure/storage/sceneStorage.ts``.
  attachScenePersistence({
    placements,
    selectedPlacementId,
    selectedProfileName,
    scaleMode,
    marginMm,
    autoOptimize,
    makeDefaultVariant: defaultVariant,
  })

  return {
    // Placements API
    placements,
    visiblePlacements,
    materializeLibraryDraft,
    selectedPlacementId,
    selectedPlacement,
    selectPlacement,
    addEmptyPlacement,
    duplicatePlacement,
    removePlacement,
    removePlacementsForFile,
    rotatePlacement,
    flipPlacement,
    // Backward-compat views
    job,
    svg,
    layers,
    visibility,
    lastFile,
    uploadWarnings,
    uploadMetadata,
    layerAlgorithms,
    currentDrawing,
    // Misc state
    loading,
    error,
    errorScope,
    changePage,
    profiles,
    selectedProfileName,
    selectedProfile,
    presets,
    selectedPresetName,
    optimizing,
    metrics,
    generating,
    gcode,
    preflighting,
    preflight,
    missingPenSlots,
    isMultiColor,
    scaleMode,
    marginMm,
    autoOptimize,
    setDrawing,
    resetDrawing,
    restorePlacementAspect,
    applyLayerAlgorithm,
    applyAlgorithmToAllLayers,
    applyLayerPasses,
    renderVariant,
    clearLayerAlgorithm,
    clearJob,
    totalLengthMm,
    totalDurationSeconds,
    effectiveSpeed,
    layerDurationSeconds,
    setVisibility,
    isVisible,
    updateLayer,
    reorderLayers,
    resnapAutoLayers,
    loadProfiles,
    loadPresets,
    saveProfile,
    deleteProfile,
    upload,
    cancelUpload,
    createPlacementFromLibrary,
    optimize,
    runPreflight,
    generate,
    flushRerender,
    // Variants
    activeVariant,
    addVariant,
    updateActiveVariant,
    renameVariant,
    removeVariant,
    setActiveVariant,
    setPlacementActiveVariant,
  }
})

function unionBoxes(boxes: BoundingBox[]): BoundingBox | null {
  if (!boxes.length) return null
  const u: BoundingBox = { x_min: Infinity, y_min: Infinity, x_max: -Infinity, y_max: -Infinity }
  for (const b of boxes) {
    u.x_min = Math.min(u.x_min, b.x_min)
    u.y_min = Math.min(u.y_min, b.y_min)
    u.x_max = Math.max(u.x_max, b.x_max)
    u.y_max = Math.max(u.y_max, b.y_max)
  }
  return Number.isFinite(u.x_min) ? u : null
}
