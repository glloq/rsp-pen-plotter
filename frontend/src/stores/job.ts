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
import { clearLivePreviewer } from '../composables/useFileManager'
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
  type LayerAlgorithmOverride,
  type LayerInfo,
  type MachineProfile,
  type Preset,
  type PreflightReport,
  type ToolpathMetrics,
} from '../api/client'
import { buildComposite } from '../lib/composite'
import {
  canonicalHex,
  layerStrokeWidthsPx,
  mmPerViewBoxUnit,
  strokeWidthMmByHex,
  svgIntrinsicPageSizeMm,
} from '../lib/penWidth'
import { assignPoolHexes } from '../lib/nearestColor'
import { resolveEffectivePalette } from '../lib/effectivePalette'
import { usePaletteSourceStore } from './paletteSource'
import { useAvailableColorsStore } from './availableColors'
import { buildPrintPlan } from '../domain/plan-builder'
import { buildTypographyPlan } from '../composables/useBitmapDraft'
import { isTextSource } from '../composables/useTypographyDraft'
import type { PrintPlan } from '../domain/print-plan'
import {
  PipelineAbortedError,
  pipelineErrorMessage,
  runGeneratePipeline,
} from '../application/runGeneratePipeline'
import { attachScenePersistence } from '../infrastructure/storage/sceneStorage'

const DEFAULT_SPEED_MM_S = 60

// Module-level memo for canonical hex normalisation. ``lengthMmByColor`` and
// ``visiblePlacements`` together walk every layer of every placement on each
// invalidation; recomputing two regex tests + string allocations per layer
// shows up on the Pi when the operator drags a slider. The map is bounded so
// it can't grow unbounded across long sessions. The actual normalisation is
// the shared ``canonicalHex`` from lib/penWidth — this wrapper only memoizes.
const _canonHexCache = new Map<string, string>()
const CANON_HEX_CACHE_MAX = 256
function canonHexMemo(value: string): string {
  const cached = _canonHexCache.get(value)
  if (cached !== undefined) return cached
  const result = canonicalHex(value)
  if (_canonHexCache.size >= CANON_HEX_CACHE_MAX) {
    const oldest = _canonHexCache.keys().next().value
    if (oldest !== undefined) _canonHexCache.delete(oldest)
  }
  _canonHexCache.set(value, result)
  return result
}

// A placement is a fully self-contained snapshot: source file metadata,
// the rendered SVG, the per-layer config, and the position/size on the
// machine workspace. Multiple placements live side-by-side on the plan
// (different files OR multiple instances of the same file). The modal
// edits one at a time — ``selectedPlacementId``.
// One pass within a multi-pass layer override.
export interface LayerPass {
  algorithm: string
  algorithm_options: Record<string, unknown>
  // Non-destructive visibility toggle (the eye in LayerPassStack).
  // ``false`` keeps the pass in the stack — so the operator can A/B and
  // re-enable it — but strips it from the /rerender payload so the
  // backend never draws it. Missing / ``true`` → enabled.
  enabled?: boolean
}

/** Passes that actually ship to the backend: ``enabled !== false``. */
export function enabledPasses(passes: readonly LayerPass[]): LayerPass[] {
  return passes.filter((pass) => pass.enabled !== false)
}

export interface LayerAlgorithm {
  algorithm: string
  algorithm_options: Record<string, unknown>
  // Optional multi-pass stack. When present and non-empty, the backend
  // renders this layer as the ordered sequence of passes (each pass is
  // an algorithm + options pair drawn against the same colour mask),
  // letting a single ink show several visual treatments at once. Empty
  // / missing → legacy single-algorithm behaviour.
  passes?: LayerPass[]
}

// Per-layer choices live directly on the placement: ``layer_algorithms``
// + ``visibility`` IS the editor state for this file. We used to wrap
// these in a list of named ``Variant`` snapshots so the operator could
// keep several styles per file and switch between them; the v0.2
// simplification cut that down to a single style per file, so the
// snapshot wrapper is gone.

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

  // Persist a placement's editor state back to the library so every
  // future placement of the same file starts from the latest snapshot.
  // No-op for placements without a library backing (legacy uploads).
  function syncPlacementToLibrary(p: Placement | null): void {
    if (!p?.library_file_id) return
    const library = useLibraryStore()
    // Persist the per-layer state + the full editor config
    // (``last_options``) so the next "Edit from library" rehydrates
    // the operator's chosen segmentation / master style / preprocess
    // instead of resetting to defaults. Also remember the on-plan
    // footprint (mm) so re-dropping the file restores the size the operator
    // left it at. Captured from "Edit from library" drafts too — the format
    // selector (fit to A5) acts on the draft — but never from an unsized
    // placement.
    const footprint_mm =
      p.width_mm > 0 && p.height_mm > 0
        ? { width_mm: p.width_mm, height_mm: p.height_mm }
        : undefined
    library.saveFileSettings(p.library_file_id, {
      layer_algorithms: p.layer_algorithms,
      visibility: p.visibility,
      last_options: p.last_options,
      footprint_mm,
    })
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

  function blankPlacement(): Placement {
    const size = defaultPlacementSize()
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

  // Fit the selected placement inside a sheet zone: uniform scale (aspect
  // preserved) so the drawing fills the page, then centre it in the zone.
  // Called by the editor's SheetPicker when the operator changes the paper
  // format — picking A3 after A5 must rescale the artwork to the new page
  // instead of leaving it at its old physical size (which only *looked*
  // right on formats smaller than the artwork, where the preview clamped
  // it to the sheet).
  function fitSelectedPlacementToSheet(sheet: {
    width_mm: number
    height_mm: number
    x_mm?: number
    y_mm?: number
  }): void {
    const p = selectedPlacement.value
    if (!p) return
    if (p.width_mm <= 0 || p.height_mm <= 0 || sheet.width_mm <= 0 || sheet.height_mm <= 0) return
    const factor = Math.min(sheet.width_mm / p.width_mm, sheet.height_mm / p.height_mm)
    const w = p.width_mm * factor
    const h = p.height_mm * factor
    const zoneX = Math.max(0, sheet.x_mm ?? 0)
    const zoneY = Math.max(0, sheet.y_mm ?? 0)
    patchSelected({
      width_mm: w,
      height_mm: h,
      x_mm: zoneX + (sheet.width_mm - w) / 2,
      y_mm: zoneY + (sheet.height_mm - h) / 2,
    })
    // The committed SVG bakes stroke widths + fill spacing derived from
    // the placement's OLD physical size (``penWidthsFor``). Re-render so
    // the plan view and Generate consume geometry adapted to the new
    // page — same pen on a bigger sheet means relatively finer, denser
    // strokes. No-op for placements without a rerender cache.
    scheduleRerender(250)
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
  // Per-layer pen tip width (viewBox units) for a placement, derived from
  // each layer's assigned colour width and the placement's mm↔unit scale.
  // Sent with /rerender so every layer's stroke matches the real pen and
  // fill spacing is floored at one pen width.
  function penWidthsFor(p: Placement): Record<string, number> {
    if (!p.svg) return {}
    const hexToMm = strokeWidthMmByHex(useAvailableColorsStore().ordered)
    if (hexToMm.size === 0) return {}
    const mmPerUnit = mmPerViewBoxUnit(p.svg, p.width_mm, p.height_mm)
    if (!mmPerUnit) return {}
    return layerStrokeWidthsPx(p.layers, hexToMm, mmPerUnit)
  }

  // Per-layer ink hex (assigned colour from magazine / inventory pool)
  // keyed by ``layer_id`` — which equals the backend label
  // ``color-{hex}`` for bitmap-derived layers. Sent with /rerender so
  // the preview SVG uses the colour that will actually be drawn rather
  // than the segmentation centroid. Layers without an assigned colour
  // (or with the same hex as the centroid) drop out of the map so the
  // backend's legacy fallback kicks in.
  function inkColorsFor(p: Placement): Record<string, string> {
    const map: Record<string, string> = {}
    for (const layer of p.layers) {
      const ink = layer.assigned_color_hex
      if (!ink) continue
      if (ink.toLowerCase() === layer.source_color.toLowerCase()) continue
      map[layer.layer_id] = ink
    }
    return map
  }

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

  // Unified debounced rerender scheduler. Coalesces all call sites onto a
  // single timer so rapid layer/colour/algorithm edits collapse to one
  // /rerender call. The shortest delay requested while a timer is pending
  // wins — a 50ms caller after a 250ms caller fires at 50ms.
  function scheduleRerender(delayMs: number): void {
    if (rerenderTimer) {
      clearTimeout(rerenderTimer)
    }
    rerenderTimer = setTimeout(() => {
      rerenderTimer = null
      trackRerender()
    }, delayMs)
  }

  // Pre-flush hooks let UI surfaces that debounce their *own*
  // ``layer_algorithms`` propagation OUTSIDE the store drain that
  // pending work before /preflight or /generate reads ``placement.svg``.
  // The style-knob sliders (MasterStyleParams / MultiColorMasterStyleParams)
  // keep a local trailing-edge timer — one propagation ~120ms after the
  // last drag input — so a slider drag doesn't patch every layer on each
  // pixel of travel. That timer is invisible to ``flushRerender``: without
  // these hooks, tweaking a style knob and immediately hitting Generate
  // raced — the local timer hadn't fired, so ``layer_algorithms`` still
  // held the previous recipe and the composite baked the OLD style into
  // the G-code while the live /preview already showed the new one.
  const flushHooks = new Set<() => void | Promise<void>>()
  function registerRerenderFlushHook(hook: () => void | Promise<void>): () => void {
    flushHooks.add(hook)
    return () => {
      flushHooks.delete(hook)
    }
  }

  // Drain any debounced + in-flight rerender so callers can safely read
  // ``placement.svg`` afterwards. Safe to call when nothing is pending.
  async function flushRerender(): Promise<void> {
    // Run component-side pre-flush hooks first so their pending
    // ``layer_algorithms`` writes + the rerender they schedule are
    // captured by the store timer drain below.
    for (const hook of [...flushHooks]) {
      try {
        await hook()
      } catch {
        // A failing hook must not strand /generate: it only means that
        // surface couldn't re-propagate, in which case the existing
        // ``layer_algorithms`` still render — just without the last tweak.
      }
    }
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
  //
  // Two things must be cleared: the mirror in ``useEditState`` (read by
  // V1 surfaces) AND the source ``previewer.previewResult`` in
  // useFileManager (read by V2's ``expertPreviewSvg``). Clearing the
  // mirror alone left V2 painting the stale render until the next
  // /preview round-trip — which only fires on the NEXT bitmap-draft
  // tweak, not on the algorithm pick the operator just made.
  function clearLivePreviewSvg(): void {
    try {
      useEditState().previewSvg.value = ''
      clearLivePreviewer()
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
    autoSyncFileSettings()
    clearLivePreviewSvg()
    scheduleRerender(250)
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
   * Render the selected placement with a single algorithm applied to
   * every layer, *without* mutating the live placement state. Powers
   * the beginner modal's live preview: the policy resolver hands us one
   * job-level recommendation and we render exactly what "Generate"
   * would produce, so the operator sees the real result before
   * committing. Returns ``null`` when there's nothing renderable (no
   * placement / job / not rerenderable) or the request was aborted.
   */
  async function previewAlgorithmOnAllLayers(
    algorithm: string,
    algorithmOptions: Record<string, unknown> = {},
    signal?: AbortSignal,
  ): Promise<{ svg: string; warnings: string[] } | null> {
    const p = selectedPlacement.value
    if (!p || !p.job_id || !p.rerenderable || !p.layers.length) return null
    const layersPayload = p.layers.map((layer) => ({
      layer_id: layer.layer_id,
      algorithm,
      algorithm_options: { ...algorithmOptions },
    }))
    try {
      const result = await rerenderJob(
        p.job_id,
        layersPayload,
        signal,
        penWidthsFor(p),
        inkColorsFor(p),
        { width_mm: p.width_mm, height_mm: p.height_mm },
      )
      return { svg: result.svg, warnings: result.warnings ?? [] }
    } catch (err) {
      if ((err as { name?: string }).name === 'CanceledError') return null
      throw err
    }
  }

  /**
   * Render the selected placement with a multi-pass stack applied to
   * every layer, *without* mutating live state. Mirror of
   * ``previewAlgorithmOnAllLayers`` for QUALITY-tier recommendations
   * that layer several passes per colour mask.
   */
  async function previewPassesOnAllLayers(
    passes: readonly LayerPass[],
    signal?: AbortSignal,
  ): Promise<{ svg: string; warnings: string[] } | null> {
    const p = selectedPlacement.value
    if (!p || !p.job_id || !p.rerenderable || !p.layers.length) return null
    const active = enabledPasses(passes)
    if (!active.length) return null
    const layersPayload = p.layers.map((layer) => ({
      layer_id: layer.layer_id,
      passes: active.map((pass) => ({
        algorithm: pass.algorithm,
        algorithm_options: { ...pass.algorithm_options },
      })),
    }))
    try {
      const result = await rerenderJob(
        p.job_id,
        layersPayload,
        signal,
        penWidthsFor(p),
        inkColorsFor(p),
        { width_mm: p.width_mm, height_mm: p.height_mm },
      )
      return { svg: result.svg, warnings: result.warnings ?? [] }
    } catch (err) {
      if ((err as { name?: string }).name === 'CanceledError') return null
      throw err
    }
  }

  /**
   * Commit a multi-pass stack to every layer of the selected placement
   * and trigger a single rerender. The beginner modal's "Generate"
   * path for QUALITY recommendations; mirrors
   * ``applyAlgorithmToAllLayers`` but writes the ``passes`` stack.
   */
  async function applyPassesToAllLayers(passes: readonly LayerPass[]): Promise<void> {
    const p = selectedPlacement.value
    if (!p || !passes.length) return
    const first = enabledPasses(passes)[0] ?? passes[0]!
    const stack = passes.map((pass) => ({
      ...pass,
      algorithm_options: { ...pass.algorithm_options },
    }))
    const next: Record<string, LayerAlgorithm> = {}
    for (const layer of p.layers) {
      next[layer.layer_id] = {
        algorithm: first.algorithm,
        algorithm_options: { ...first.algorithm_options },
        passes: stack.map((pass) => ({
          ...pass,
          algorithm_options: { ...pass.algorithm_options },
        })),
      }
    }
    patchSelected({ layer_algorithms: next })
    autoSyncFileSettings()
    clearLivePreviewSvg()
    scheduleRerender(50)
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
    autoSyncFileSettings()
    clearLivePreviewSvg()
    scheduleRerender(50)
  }

  async function clearLayerAlgorithm(layerId: string): Promise<void> {
    const p = selectedPlacement.value
    if (!p) return
    if (!(layerId in p.layer_algorithms)) return
    const next = { ...p.layer_algorithms }
    delete next[layerId]
    patchSelected({ layer_algorithms: next })
    autoSyncFileSettings()
    clearLivePreviewSvg()
    scheduleRerender(250)
  }

  // Apply a multi-pass stack to one layer: ``passes`` is the ordered list
  // of algorithms (with options) drawn against the same colour mask. The
  // first pass plots first, the last on top — order is preserved in the
  // toolpath. An empty list clears the override (same as clearLayerAlgorithm).
  // Disabled passes (``enabled === false``) are KEPT in state — they're a
  // non-destructive A/B toggle — and only stripped when building the
  // /rerender payload (see triggerRerender).
  async function applyLayerPasses(layerId: string, passes: LayerPass[]): Promise<void> {
    const p = selectedPlacement.value
    if (!p) return
    if (!passes.length) {
      await clearLayerAlgorithm(layerId)
      return
    }
    // Mirror the first enabled pass into the legacy algorithm/options
    // fields so existing UI that reads ``layer_algorithms[id].algorithm``
    // (e.g. PrintStylePicker highlighting) still surfaces the dominant
    // pass. Fall back to the first pass when everything is disabled.
    const first = enabledPasses(passes)[0] ?? passes[0]!
    patchSelected({
      layer_algorithms: {
        ...p.layer_algorithms,
        [layerId]: {
          algorithm: first.algorithm,
          algorithm_options: { ...first.algorithm_options },
          // Share the pass objects (no deep copy) so LayerPassStack's
          // per-row WeakMap keys stay stable across the emit → store →
          // props round-trip; the component never mutates a pass in
          // place (every edit builds a fresh object).
          passes: [...passes],
        },
      },
    })
    autoSyncFileSettings()
    clearLivePreviewSvg()
    scheduleRerender(250)
  }

  async function triggerRerender(): Promise<void> {
    const p = selectedPlacement.value
    if (!p || !p.job_id || !p.svg) return
    // Vector sources (PDF / HTML / DOCX / SVG / DXF / EPS) have no
    // segmentation cache for the backend's /rerender route — the
    // editor's layer-algorithm tweaks land on the next full re-upload
    // instead. Calling /rerender here would always 404 and surface the
    // misleading "cache expiré" toast right after a successful
    // Re-convertir.
    if (!p.rerenderable) return
    if (rerenderController) rerenderController.abort()
    const controller = new AbortController()
    rerenderController = controller
    // Per-rerender timing fuels the ``preview_refresh`` KPI in the
    // perf overlay (roadmap C.8). Aborted rerenders don't emit a
    // sample — the operator's intent was to cancel, not to observe.
    const perf = usePerfStore()
    const tStart = performance.now()
    try {
      const layersPayload = Object.entries(p.layer_algorithms).flatMap(
        ([layer_id, spec]): LayerAlgorithmOverride[] => {
          // Multi-pass stack: send ``passes`` so the backend stacks the
          // algorithms; the legacy single-algorithm fields stay populated
          // for back-compat but the backend prefers ``passes`` when set.
          // Disabled passes are a non-destructive UI toggle — they stay in
          // state but never ship to the backend. A stack whose passes are
          // ALL disabled sends no override at all, so the layer falls back
          // to its default conversion (same as a cleared stack) while the
          // operator can still re-enable any pass.
          if (spec.passes && spec.passes.length) {
            const active = enabledPasses(spec.passes)
            if (!active.length) return []
            return [
              {
                layer_id,
                passes: active.map((p) => ({
                  algorithm: p.algorithm,
                  algorithm_options: p.algorithm_options,
                })),
              },
            ]
          }
          return [
            {
              layer_id,
              algorithm: spec.algorithm,
              algorithm_options: spec.algorithm_options,
            },
          ]
        },
      )
      const result = await rerenderJob(
        p.job_id,
        layersPayload,
        controller.signal,
        penWidthsFor(p),
        inkColorsFor(p),
        { width_mm: p.width_mm, height_mm: p.height_mm },
      )
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

  // Aggregate drawn length (mm) per assigned colour, keyed by canonical
  // lowercase 6-digit hex so the available-colours inventory (which stores
  // canonical hex) can surface "metres used" for each ink. A layer with no
  // explicit ``assigned_color_hex`` falls back to its source colour, matching
  // what actually gets drawn on the sheet.
  const lengthMmByColor = computed<Record<string, number>>(() => {
    const totals: Record<string, number> = {}
    for (const placement of visiblePlacements.value) {
      for (const layer of placement.layers) {
        const hex = canonHexMemo(layer.assigned_color_hex ?? layer.source_color)
        totals[hex] = (totals[hex] ?? 0) + layer.total_length_mm
      }
    }
    return totals
  })

  function setVisibility(layerId: string, visible: boolean): void {
    const p = selectedPlacement.value
    if (!p) return
    patchSelected({ visibility: { ...p.visibility, [layerId]: visible } })
    autoSyncFileSettings()
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
    // Picking a new ink for a layer (assigned_color_hex / color_assignment)
    // changes what the rendered SVG should look like. Schedule a debounced
    // rerender so the canvas reflects the new colour without waiting for
    // the next algorithm tweak. Same display-priority trap as
    // ``applyLayerAlgorithm``: the live /preview SVG ignores per-layer ink
    // assignments and would keep masking the recoloured /rerender result
    // in the expert editor, so clear it first.
    if ('assigned_color_hex' in patch || 'color_assignment' in patch) {
      clearLivePreviewSvg()
      scheduleRerender(250)
    }
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

  // Re-assign every ``auto`` layer (across ALL placements) to an ink from
  // the active pool, preserving ``manual`` overrides. Called when the
  // operator changes the palette source or swaps the installed pens so the
  // assigned colours follow the pool they just selected — without this the
  // colours stayed pinned to whatever the profile-agnostic upload picked.
  // Uses the same unique-while-possible greedy matching as the backend's
  // ``auto_assign_layer_colors`` (per placement) so 6 clusters against 6
  // pens come out as 6 distinct inks instead of piling onto the 2-3
  // nearest pens. An empty pool clears the auto value
  // (assigned_color_hex = null), which matches the backend's fallback to
  // the raw centroid.
  // True when a placement was converted in "fidèle à l'image" mode — an
  // image-clustering segmentation (kmeans / kmeans_lab) committed WITHOUT
  // an ``ink_pool``. That combination means the operator deliberately chose
  // to render the photo's own colours rather than follow the pen rack, so
  // its auto layers must NOT be snapped onto the owned pool: snapping would
  // override the faithful centroids with the few closest pens (the
  // "mauvaises couleurs" report). The pens-follow path always ships an
  // ``ink_pool`` (wired as kmeans_lab + remap), so it's excluded here and
  // keeps snapping as before.
  function placementUsesImageColors(p: { last_options?: Record<string, unknown> | null }): boolean {
    const opts = (p.last_options ?? {}) as Record<string, unknown>
    const method = opts.segmentation_method
    const inkPool = opts.ink_pool
    const hasPool = Array.isArray(inkPool) && inkPool.length > 0
    return !hasPool && (method === 'kmeans' || method === 'kmeans_lab')
  }

  function resnapAutoLayers(poolOverride?: readonly string[]): void {
    const basePool = poolOverride ?? currentEffectivePalette()
    let changed = false
    placements.value = placements.value.map((p) => {
      // Image-colours placements snap against an empty pool → every auto
      // layer clears to ``null`` and falls back to its faithful centroid.
      const pool = placementUsesImageColors(p) ? [] : basePool
      const assignments = pool.length
        ? assignPoolHexes(
            p.layers.map((layer) => ({
              sourceHex: layer.source_color,
              pinnedHex: layer.color_assignment === 'manual' ? layer.assigned_color_hex : null,
            })),
            pool,
          )
        : p.layers.map(() => null)
      let touched = false
      const layers = p.layers.map((layer, i) => {
        if (layer.color_assignment === 'manual') return layer
        const next = assignments[i] ?? null
        if ((layer.assigned_color_hex ?? null) === next) return layer
        touched = true
        return { ...layer, assigned_color_hex: next, color_assignment: 'auto' as const }
      })
      if (!touched) return p
      changed = true
      return { ...p, layers }
    })
    if (changed) {
      invalidateOutputs()
      // Re-render the selected placement so the canvas/preview SVG
      // reflects the new assigned inks. Without this the operator sees
      // the stale centroid colours until the next algorithm tweak.
      scheduleRerender(50)
    }
  }

  watch([scaleMode, marginMm, selectedProfileName], invalidateOutputs)

  // Remember a library-backed placement's footprint whenever the operator
  // resizes it (drag handles) or refits it to a sheet (the editor's A5/A4
  // picker — which acts on the selected placement, including an "Edit from
  // library" draft). The signature keys on size only — a position-only move
  // leaves it unchanged, so dragging a placement around doesn't churn the
  // settings store. ``saveFileSettings`` is itself debounced, so a live
  // resize gesture collapses to a single write. Restored on the next drop
  // (``createPlacementFromLibrary``) so the file comes back at the size it
  // was left at instead of an auto-fit-to-workspace size.
  watch(
    () => {
      const p = selectedPlacement.value
      if (!p || !p.library_file_id) return null
      if (!(p.width_mm > 0) || !(p.height_mm > 0)) return null
      return `${p.library_file_id}|${p.id}|${p.width_mm}|${p.height_mm}`
    },
    (sig) => {
      if (sig) syncPlacementToLibrary(selectedPlacement.value)
    },
  )

  // Re-snap auto layers whenever the active pool changes — the operator
  // toggled the palette source (pens / available / union), edited the
  // available-colours inventory, or swapped the installed pens. Keying the
  // watcher on the serialised palette means a no-op change (same swatches)
  // doesn't churn; ``resnapAutoLayers`` itself only patches layers that
  // actually move, so manual overrides and unchanged autos stay put.
  // Cheap allocation-free hash of the current palette so the watch below
  // skips redundant re-snaps without paying a full ``join('|')`` string
  // allocation per dependency tick. Walks every swatch (so a middle-slot
  // swap still triggers) but folds into a single 32-bit accumulator —
  // 30x cheaper on Pi than the previous ``Array#join``.
  function paletteSignature(): number {
    const p = currentEffectivePalette()
    let h = p.length | 0
    for (let i = 0; i < p.length; i++) {
      const swatch = p[i]!
      for (let j = 0; j < swatch.length; j++) {
        h = (h * 31 + swatch.charCodeAt(j)) | 0
      }
    }
    return h
  }
  watch(
    () => paletteSignature(),
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
      // Preserve the current footprint across a re-convert (the editor's
      // Apply / "Enregistrer le style") so changing the algorithm or style
      // doesn't resize the artwork on the plan. A fresh placement (no prior
      // conversion) has no meaningful size yet, so it auto-sizes from the
      // content / page instead.
      const current = placements.value.find((p) => p.id === targetId)
      const keepSize =
        current?.source_file && current.width_mm > 0 && current.height_mm > 0
          ? { width_mm: current.width_mm, height_mm: current.height_mm }
          : null
      const layoutPatch = computeInitialLayout(
        sourceBbox,
        targetId,
        intrinsicPageSize(detail.upload_metadata),
        detail.svg,
        keepSize,
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
    // If this library entry has previously-saved settings, hydrate them
    // onto the new placement so the file renders with its last-used print
    // settings instead of the default conversion. Otherwise fall back to
    // a fresh default variant generated by ``blankPlacement``.
    const saved = library.getFileSettings(detail.file_id)
    // Restore the operator's last on-plan footprint — set by a resize or
    // the editor's sheet picker (fit to A5). Applies to "Edit from library"
    // drafts too: the format selector acts on the draft, so the draft must
    // open at (and keep) the saved size, otherwise reopening the editor
    // would clobber it with a fresh auto-fit. computeInitialLayout clamps
    // it to the current bed.
    const preferredSize = saved?.footprint_mm
    const layoutPatch = computeInitialLayout(
      sourceBbox,
      placement.id,
      intrinsicPageSize(detail.upload_metadata),
      detail.svg,
      preferredSize,
    )
    const settingsPatch: Partial<Placement> = {}
    if (saved && Object.keys(saved.layer_algorithms).length > 0) {
      settingsPatch.layer_algorithms = { ...saved.layer_algorithms }
    }
    // Restore the saved editor config so the modal opens showing the
    // chosen segmentation / master style / preprocess the operator last
    // applied to this file, instead of resetting the draft to defaults.
    // ``rehydrateDraft`` reads ``placement.last_options`` directly.
    if (saved?.last_options) {
      settingsPatch.last_options = { ...saved.last_options }
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
      // map so layers the operator had hidden stay hidden.
      visibility: {
        ...Object.fromEntries(detail.layers.map((l) => [l.layer_id, true])),
        ...(saved?.visibility ?? {}),
      },
      ...layoutPatch,
      ...settingsPatch,
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
    if (saved && Object.keys(saved.layer_algorithms).length > 0) {
      scheduleRerender(50)
    }
    return placement.id
  }

  function computeInitialLayout(
    sourceBbox: BoundingBox,
    placementId: string,
    intrinsicSize?: { width_mm: number; height_mm: number } | null,
    svg?: string,
    preferredSizeMm?: { width_mm: number; height_mm: number } | null,
  ): Partial<Placement> {
    const profile = selectedProfile.value
    if (!profile) return {}
    const ws = profile.workspace
    const wsW = ws.x_max - ws.x_min
    const wsH = ws.y_max - ws.y_min
    const usableW = Math.max(wsW - 2 * marginMm.value, wsW * 0.5)
    const usableH = Math.max(wsH - 2 * marginMm.value, wsH * 0.5)
    const bboxW = Math.max(sourceBbox.x_max - sourceBbox.x_min, 1e-6)
    const bboxH = Math.max(sourceBbox.y_max - sourceBbox.y_min, 1e-6)
    // Size the placement to the *inked* bbox converted to millimetres,
    // then clamp down (never up) if it overflows the usable area. The
    // mm↔viewBox-unit bridge is what makes the result a real-world size
    // rather than a fit-to-workspace rescale.
    const sizeToContent = (mmPerUnit: number): { width: number; height: number } => {
      const contentW = bboxW * mmPerUnit
      const contentH = bboxH * mmPerUnit
      const fit = Math.min(1, usableW / contentW, usableH / contentH)
      return { width: contentW * fit, height: contentH * fit }
    }
    let width: number
    let height: number
    if (preferredSizeMm && preferredSizeMm.width_mm > 0 && preferredSizeMm.height_mm > 0) {
      // Restore the operator's last-saved footprint (a resize or a sheet
      // refit like "fit to A5"), clamped down — never up — so it still
      // fits the current bed. This wins over the bbox/page computation
      // below because an explicit size is a deliberate choice the auto
      // layout must not override.
      const fit = Math.min(
        1,
        usableW / preferredSizeMm.width_mm,
        usableH / preferredSizeMm.height_mm,
      )
      width = preferredSizeMm.width_mm * fit
      height = preferredSizeMm.height_mm * fit
    } else if (intrinsicSize && intrinsicSize.width_mm > 0 && intrinsicSize.height_mm > 0 && svg) {
      // PDF / DOCX / HTML / text: the converter reports the page size in
      // ``upload_metadata`` and emits a page-sized SVG (PyMuPDF viewBox in
      // points, Hershey viewBox in mm) with the content offset from the
      // page corner by its margins. ``mmPerViewBoxUnit`` reads the SVG's
      // viewBox vs the reported page dimensions to bridge units into
      // millimetres.
      const mmPerUnit = mmPerViewBoxUnit(svg, intrinsicSize.width_mm, intrinsicSize.height_mm) ?? 1
      ;({ width, height } = sizeToContent(mmPerUnit))
    } else {
      // Raw SVG (Inkscape / Illustrator export) reports no page metadata,
      // but its root ``<svg width/height>`` still encodes the physical
      // page it was drawn for. Honour that so an A4 / A5 drawing lands at
      // its true mm size; without it the content bbox is rescaled to fill
      // the workspace and an A4 file comes in at the wrong size. ``px`` /
      // unitless dimensions yield null here and keep the fit fallback.
      const svgPage = svg ? svgIntrinsicPageSizeMm(svg) : null
      const mmPerUnit =
        svg && svgPage ? mmPerViewBoxUnit(svg, svgPage.width_mm, svgPage.height_mm) : null
      if (mmPerUnit) {
        ;({ width, height } = sizeToContent(mmPerUnit))
      } else {
        const scale = Math.min(usableW / bboxW, usableH / bboxH)
        width = bboxW * scale
        height = bboxH * scale
      }
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
    // Single-flight guard (same as upload): a double-click on the page
    // chevrons would otherwise race two /upload round-trips against the
    // same placement and interleave their patches.
    if (loading.value) return
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
      const layoutPatch = computeInitialLayout(sourceBbox, targetId, intrinsic, result.svg)
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
    // ``isTextSource`` (not "any mime") so a mixed scene (image + text)
    // attaches the typography plan to the actual text placement instead
    // of silently dropping it because the first placement was a raster.
    const textPlacement = ready.find((p) => isTextSource(p.source_mime))
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
    // Disable re-entry synchronously: flushRerender + plan-build run for
    // several seconds before the progress modal appears, and the Generate
    // button's :disabled binding watches this flag — without the early
    // flip the operator can fire several pipelines in parallel.
    if (generating.value) return
    generating.value = true

    // Wait for any pending /rerender to land first — otherwise the
    // composite would bake in the previous variant's SVG, and the
    // operator would be confused why their just-picked print style
    // didn't make it into the toolpath.
    await flushRerender()

    // Mirror buildPlanPayload's filter: library drafts never reach the
    // plan, so they must not count toward readiness either — otherwise a
    // drafts-only scene passes the gate and the pipeline errors out on a
    // null plan.
    const ready = placements.value.some((p) => !p.is_library_draft && p.svg && p.layers.length)
    if (!ready) {
      generating.value = false
      return
    }

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
  // ====== File-settings sync ============================================
  // The placement's live ``layer_algorithms`` + ``visibility`` IS the
  // single style we keep per file. Whenever a layer mutation lands we
  // mirror the latest state back to the library so the next "Edit
  // from library" reopens with exactly what the operator just set.
  function autoSyncFileSettings(): void {
    syncPlacementToLibrary(selectedPlacement.value)
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
    fitSelectedPlacementToSheet,
    applyLayerAlgorithm,
    applyAlgorithmToAllLayers,
    previewAlgorithmOnAllLayers,
    applyPassesToAllLayers,
    previewPassesOnAllLayers,
    applyLayerPasses,
    clearLayerAlgorithm,
    clearJob,
    totalLengthMm,
    totalDurationSeconds,
    lengthMmByColor,
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
    registerRerenderFlushHook,
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
