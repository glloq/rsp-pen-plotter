import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { errorDetail } from '../api/error'
import { i18n } from '../i18n'
import { useLibraryStore } from './library'
import { useToastStore } from './toasts'
import {
  deleteProfile as apiDeleteProfile,
  saveProfile as apiSaveProfile,
  generateGcode,
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

const DEFAULT_SPEED_MM_S = 60

// A placement is a fully self-contained snapshot: source file metadata,
// the rendered SVG, the per-layer config, and the position/size on the
// machine workspace. Multiple placements live side-by-side on the plan
// (different files OR multiple instances of the same file). The modal
// edits one at a time — ``selectedPlacementId``.
interface LayerAlgorithm {
  algorithm: string
  algorithm_options: Record<string, unknown>
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
  variants: Variant[]
  active_variant_id: string
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

  function patchPlacement(id: string, patch: Partial<Placement>): void {
    placements.value = placements.value.map((p) => (p.id === id ? { ...p, ...patch } : p))
  }
  function patchSelected(patch: Partial<Placement>): void {
    const id = selectedPlacementId.value
    if (!id) return
    patchPlacement(id, patch)
    preflight.value = null
  }

  function selectPlacement(id: string | null): void {
    selectedPlacementId.value = id
  }

  function removePlacement(id: string): void {
    placements.value = placements.value.filter((p) => p.id !== id)
    if (selectedPlacementId.value === id) {
      selectedPlacementId.value = placements.value[0]?.id ?? null
    }
    preflight.value = null
    gcode.value = null
  }

  function defaultPlacementSize(): { x_mm: number; y_mm: number; width_mm: number; height_mm: number } {
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
      ...size,
    }
  }

  function addEmptyPlacement(): string {
    const placement = blankPlacement()
    placements.value = [...placements.value, placement]
    selectedPlacementId.value = placement.id
    return placement.id
  }

  function duplicatePlacement(id: string, offsetMm = 15): string | null {
    const src = placements.value.find((p) => p.id === id)
    if (!src) return null
    // Cloned placements get their own variant identities so renaming /
    // updating one doesn't bleed into the other. Live state is also
    // cloned so tweaks on one don't bleed into the other.
    const clonedVariants = src.variants.map((v) => ({
      ...v,
      id: newVariantId(),
      layer_algorithms: { ...v.layer_algorithms },
      visibility: { ...v.visibility },
    }))
    const activeIdx = src.variants.findIndex((v) => v.id === src.active_variant_id)
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
      active_variant_id: clonedVariants[activeIdx >= 0 ? activeIdx : 0]?.id ?? clonedVariants[0]!.id,
    }
    placements.value = [...placements.value, clone]
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

  const scaleMode = ref<'fit' | 'actual'>('fit')
  const marginMm = ref(10)
  const autoOptimize = ref(true)

  const selectedProfile = computed(
    () => profiles.value.find((p) => p.name === selectedProfileName.value) ?? null,
  )

  const isMultiColor = computed<boolean>(
    () => (selectedProfile.value?.pen_slot_count ?? 1) > 1,
  )

  // ====== /rerender ======================================================
  let rerenderController: AbortController | null = null
  let rerenderTimer: ReturnType<typeof setTimeout> | null = null

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
    if (rerenderTimer) clearTimeout(rerenderTimer)
    rerenderTimer = setTimeout(triggerRerender, 250)
  }

  async function clearLayerAlgorithm(layerId: string): Promise<void> {
    const p = selectedPlacement.value
    if (!p) return
    if (!(layerId in p.layer_algorithms)) return
    const next = { ...p.layer_algorithms }
    delete next[layerId]
    patchSelected({ layer_algorithms: next })
    if (rerenderTimer) clearTimeout(rerenderTimer)
    rerenderTimer = setTimeout(triggerRerender, 250)
  }

  async function triggerRerender(): Promise<void> {
    const p = selectedPlacement.value
    if (!p || !p.job_id || !p.svg) return
    if (rerenderController) rerenderController.abort()
    const controller = new AbortController()
    rerenderController = controller
    try {
      const layersPayload = Object.entries(p.layer_algorithms).map(
        ([layer_id, spec]) => ({
          layer_id,
          algorithm: spec.algorithm,
          algorithm_options: spec.algorithm_options,
        }),
      )
      const result = await rerenderJob(p.job_id, layersPayload, controller.signal)
      if (controller.signal.aborted) return
      patchPlacement(p.id, { svg: result.svg })
      // Generation needs to be redone for the new SVG.
      metrics.value = null
      gcode.value = null
      preflight.value = null
    } catch (err) {
      if (controller.signal.aborted) return
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 404) {
        // silent — cache evicted; re-upload to refresh
      } else if (status === 405) {
        const toasts = useToastStore()
        toasts.warning(i18n.global.t('layers.rerenderUnavailable'))
      } else {
        const toasts = useToastStore()
        toasts.warning((err as Error).message || i18n.global.t('layers.rerenderFailed'))
      }
    } finally {
      if (rerenderController === controller) rerenderController = null
    }
  }

  // ====== Per-layer utilities (act on selected) ==========================
  const missingPenSlots = computed<number[]>(() => {
    const profile = selectedProfile.value
    if (!profile) return []
    const hasExplicit = (profile.pens?.length ?? 0) > 0
    const installed = new Set(
      (profile.pens ?? []).filter((p) => p.installed).map((p) => p.index),
    )
    const missing = new Set<number>()
    for (const placement of placements.value) {
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
    return layer.drawing_speed_mm_s ?? selectedProfile.value?.drawing_speed_mm_s ?? DEFAULT_SPEED_MM_S
  }

  function layerDurationSeconds(layer: LayerInfo): number {
    const speed = effectiveSpeed(layer)
    return speed > 0 ? layer.total_length_mm / speed : 0
  }

  const totalLengthMm = computed(() =>
    placements.value.reduce(
      (sum, p) => sum + p.layers.reduce((s, l) => s + l.total_length_mm, 0),
      0,
    ),
  )

  const totalDurationSeconds = computed(() =>
    placements.value.reduce(
      (sum, p) => sum + p.layers.reduce((s, l) => s + layerDurationSeconds(l), 0),
      0,
    ),
  )

  function setVisibility(layerId: string, visible: boolean): void {
    const p = selectedPlacement.value
    if (!p) return
    patchSelected({ visibility: { ...p.visibility, [layerId]: visible } })
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

  watch([scaleMode, marginMm, selectedProfileName], () => {
    preflight.value = null
  })
  watch(placements, () => {
    preflight.value = null
  }, { deep: true })

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
  async function upload(file: File, optionsOverride?: Record<string, unknown>): Promise<void> {
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
    metrics.value = null
    gcode.value = null
    preflight.value = null
    const toasts = useToastStore()
    const library = useLibraryStore()
    try {
      const result = await library.upload(file, { convertOptions: options })
      if (!result) {
        throw new Error(i18n.global.t('upload.failed'))
      }
      const detail = result.file
      const bboxes = detail.layers.map((l) => l.bbox)
      const sourceBbox = unionBoxes(bboxes) ?? emptyBbox()
      const layoutPatch = computeInitialLayout(sourceBbox, targetId)
      patchPlacement(targetId, {
        library_file_id: detail.file_id,
        source_file: detail.source_file,
        source_mime: detail.source_mime,
        // ``file_id`` doubles as the cache key for /rerender (see api/files.py).
        job_id: detail.file_id,
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
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('upload.failed'))
      error.value = message
      errorScope.value = 'upload'
      // Reset svg/layers on the target placement so the UI shows the
      // drop-zone again instead of stale content.
      patchPlacement(targetId, { svg: '', layers: [] })
      toasts.error(message)
    } finally {
      loading.value = false
    }
  }

  // Create a new placement on the plan from an existing library entry.
  // ``position`` (workspace mm) centres the placement on that point; when
  // omitted, the placement is centred on the workspace.
  async function createPlacementFromLibrary(
    fileId: string,
    position?: { x: number; y: number },
  ): Promise<string | null> {
    const library = useLibraryStore()
    const detail = await library.ensureDetail(fileId)
    if (!detail) return null
    const placement = blankPlacement()
    const bboxes = detail.layers.map((l) => l.bbox)
    const sourceBbox = unionBoxes(bboxes) ?? emptyBbox()
    placements.value = [...placements.value, placement]
    selectedPlacementId.value = placement.id
    const layoutPatch = computeInitialLayout(sourceBbox, placement.id)
    patchPlacement(placement.id, {
      library_file_id: detail.file_id,
      source_file: detail.source_file,
      source_mime: detail.source_mime,
      job_id: detail.file_id,
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
    return placement.id
  }

  function computeInitialLayout(
    sourceBbox: BoundingBox,
    placementId: string,
  ): Partial<Placement> {
    const profile = selectedProfile.value
    if (!profile) return {}
    const ws = profile.workspace
    const wsW = ws.x_max - ws.x_min
    const wsH = ws.y_max - ws.y_min
    const bboxW = Math.max(sourceBbox.x_max - sourceBbox.x_min, 1e-6)
    const bboxH = Math.max(sourceBbox.y_max - sourceBbox.y_min, 1e-6)
    const usableW = Math.max(wsW - 2 * marginMm.value, wsW * 0.5)
    const usableH = Math.max(wsH - 2 * marginMm.value, wsH * 0.5)
    const scale = Math.min(usableW / bboxW, usableH / bboxH)
    const width = bboxW * scale
    const height = bboxH * scale
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

  function clearJob(): void {
    placements.value = []
    selectedPlacementId.value = null
    metrics.value = null
    gcode.value = null
    preflight.value = null
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
    if (!p?.last_file) return
    const targetId = p.id
    const next = { ...(p.last_options ?? {}), page }
    loading.value = true
    error.value = null
    errorScope.value = null
    patchPlacement(targetId, { last_options: next })
    try {
      const result = await uploadFile(p.last_file, selectedProfileName.value, next)
      const bboxes = result.job.layers.map((l) => l.bbox)
      const sourceBbox = unionBoxes(bboxes) ?? emptyBbox()
      const layoutPatch = computeInitialLayout(sourceBbox, targetId)
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
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('upload.failed'))
      error.value = message
      errorScope.value = 'upload'
      useToastStore().error(message)
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
    } catch (err) {
      error.value = errorDetail(err, i18n.global.t('layers.optimizeFailed'))
      errorScope.value = 'optimize'
    } finally {
      optimizing.value = false
    }
  }

  function compositePayload(): {
    svg: string
    layers: LayerInfo[]
    placement: { sheet_width_mm: number; sheet_height_mm: number; offset_x_mm: number; offset_y_mm: number } | null
  } | null {
    const profile = selectedProfile.value
    if (!profile) return null
    const ready = placements.value.filter((p) => p.svg && p.layers.length)
    if (!ready.length) return null
    const result = buildComposite(ready, profile)
    // The backend ``_make_transform`` centres the drawing on the
    // drawable region. To preserve the absolute workspace coordinates
    // we baked into the composite, define the region to be exactly the
    // union of the rendered layer bboxes — region_center then matches
    // bbox_center and the transform collapses to identity.
    const bbox = unionBoxes(result.layers.map((l) => l.bbox))
    let placement: ReturnType<typeof compositePayload> extends infer R
      ? R extends { placement: infer P } ? P : never : never = null
    if (bbox) {
      const ws = profile.workspace
      placement = {
        offset_x_mm: Math.max(0, bbox.x_min - ws.x_min),
        offset_y_mm: Math.max(0, bbox.y_min - ws.y_min),
        sheet_width_mm: Math.max(1e-3, bbox.x_max - bbox.x_min),
        sheet_height_mm: Math.max(1e-3, bbox.y_max - bbox.y_min),
      }
    }
    return { svg: result.svg, layers: result.layers, placement }
  }

  async function runPreflight(): Promise<void> {
    const payload = compositePayload()
    if (!payload) return
    preflighting.value = true
    error.value = null
    errorScope.value = null
    try {
      preflight.value = await preflightCheck(
        payload.svg,
        selectedProfileName.value,
        payload.layers.map((layer) => ({
          layer_id: layer.layer_id,
          target_pen_slot: layer.target_pen_slot,
          drawing_speed_mm_s: layer.drawing_speed_mm_s,
          source_color: layer.source_color,
          color_label: layer.color_label,
          pause_before: layer.pause_before,
        })),
        'actual',
        0,
        payload.placement,
      )
    } catch (err) {
      preflight.value = null
      error.value = errorDetail(err, i18n.global.t('preflight.failed'))
      errorScope.value = 'generate'
    } finally {
      preflighting.value = false
    }
  }

  async function generate(): Promise<void> {
    const payload = compositePayload()
    if (!payload) return
    generating.value = true
    error.value = null
    errorScope.value = null
    try {
      const result = await generateGcode(
        payload.svg,
        selectedProfileName.value,
        payload.layers.map((layer) => ({
          layer_id: layer.layer_id,
          target_pen_slot: layer.target_pen_slot,
          drawing_speed_mm_s: layer.drawing_speed_mm_s,
          source_color: layer.source_color,
          color_label: layer.color_label,
          pause_before: layer.pause_before,
        })),
        'actual',
        0,
        payload.placement,
      )
      gcode.value = result.gcode
    } catch (err) {
      error.value = errorDetail(err, i18n.global.t('layers.generateFailed'))
      errorScope.value = 'generate'
    } finally {
      generating.value = false
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
  }

  function renameVariant(variantId: string, name: string): void {
    const p = selectedPlacement.value
    if (!p) return
    const trimmed = name.trim() || i18n.global.t('variants.untitled')
    patchSelected({
      variants: p.variants.map((v) => (v.id === variantId ? { ...v, name: trimmed } : v)),
    })
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
    rerenderTimer = setTimeout(triggerRerender, 50)
  }

  function setActiveVariant(variantId: string): void {
    const p = selectedPlacement.value
    if (!p) return
    const target = p.variants.find((v) => v.id === variantId)
    if (!target) return
    patchSelected({ active_variant_id: variantId })
    loadVariantState(target)
  }

  const SCENE_KEY = 'omniplot.scene.v4'
  const LEGACY_SCENE_KEYS = ['omniplot.scene.v3', 'omniplot.scene.v2']

  interface SerializableScene {
    placements: Placement[]
    selectedPlacementId: string | null
    selectedProfileName: string
    scaleMode: 'fit' | 'actual'
    marginMm: number
    autoOptimize: boolean
  }

  function persistScene(): void {
    try {
      const data: SerializableScene = {
        // ``last_file`` is a File handle — can't survive JSON.
        placements: placements.value.map((p) => ({ ...p, last_file: null })),
        selectedPlacementId: selectedPlacementId.value,
        selectedProfileName: selectedProfileName.value,
        scaleMode: scaleMode.value,
        marginMm: marginMm.value,
        autoOptimize: autoOptimize.value,
      }
      localStorage.setItem(SCENE_KEY, JSON.stringify(data))
    } catch {
      // localStorage may be unavailable (private browsing) or full.
    }
  }

  function hydrateScene(): void {
    try {
      let raw = localStorage.getItem(SCENE_KEY)
      let migratingFrom: string | null = null
      if (!raw) {
        for (const legacy of LEGACY_SCENE_KEYS) {
          const legacyRaw = localStorage.getItem(legacy)
          if (legacyRaw) {
            raw = legacyRaw
            migratingFrom = legacy
            break
          }
        }
        if (!raw) return
      }
      const data = JSON.parse(raw) as Partial<SerializableScene>
      if (Array.isArray(data.placements)) {
        placements.value = data.placements.map((p) => {
          // Default the new ``library_file_id`` field for placements
          // persisted before the library existed.
          const placement = {
            ...({ library_file_id: null } as Pick<Placement, 'library_file_id'>),
            ...p,
            last_file: null,
          } as Placement
          // v2 → v3 migration: wrap legacy placement state in a default
          // variant so the variant API has a snapshot to point at.
          if (!Array.isArray(placement.variants) || !placement.variants.length) {
            const variant: Variant = {
              id: newVariantId(),
              name: i18n.global.t('variants.default'),
              layer_algorithms: { ...(placement.layer_algorithms ?? {}) },
              visibility: { ...(placement.visibility ?? {}) },
            }
            placement.variants = [variant]
            placement.active_variant_id = variant.id
          }
          return placement
        })
      }
      if (data.selectedPlacementId !== undefined) {
        selectedPlacementId.value = data.selectedPlacementId
      }
      if (data.selectedProfileName) selectedProfileName.value = data.selectedProfileName
      if (data.scaleMode) scaleMode.value = data.scaleMode
      if (typeof data.marginMm === 'number') marginMm.value = data.marginMm
      if (typeof data.autoOptimize === 'boolean') autoOptimize.value = data.autoOptimize
      if (migratingFrom) {
        for (const legacy of LEGACY_SCENE_KEYS) localStorage.removeItem(legacy)
        persistScene()
      }
    } catch {
      // Malformed JSON / no localStorage — start fresh.
    }
  }

  let persistTimer: ReturnType<typeof setTimeout> | null = null
  function schedulePersist(): void {
    if (persistTimer) clearTimeout(persistTimer)
    persistTimer = setTimeout(persistScene, 300)
  }

  hydrateScene()
  watch(
    [placements, selectedPlacementId, selectedProfileName, scaleMode, marginMm, autoOptimize],
    schedulePersist,
    { deep: true },
  )

  return {
    // Placements API
    placements,
    selectedPlacementId,
    selectedPlacement,
    selectPlacement,
    addEmptyPlacement,
    duplicatePlacement,
    removePlacement,
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
    applyLayerAlgorithm,
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
    loadProfiles,
    loadPresets,
    saveProfile,
    deleteProfile,
    upload,
    createPlacementFromLibrary,
    optimize,
    runPreflight,
    generate,
    // Variants
    activeVariant,
    addVariant,
    updateActiveVariant,
    renameVariant,
    removeVariant,
    setActiveVariant,
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
