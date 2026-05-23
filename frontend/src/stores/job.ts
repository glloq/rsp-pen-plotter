import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { errorDetail } from '../api/error'
import { i18n } from '../i18n'
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
  type Job,
  type LayerInfo,
  type MachineProfile,
  type Preset,
  type PreflightReport,
  type ToolpathMetrics,
} from '../api/client'

const DEFAULT_SPEED_MM_S = 60

export const useJobStore = defineStore('job', () => {
  const job = ref<Job | null>(null)
  const svg = ref<string | null>(null)
  const layers = ref<LayerInfo[]>([])
  const visibility = ref<Record<string, boolean>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)
  const errorScope = ref<'upload' | 'optimize' | 'generate' | null>(null)
  const uploadWarnings = ref<string[]>([])
  // Converter-provided metadata, e.g. ``page_count`` and the current ``page``
  // for multi-page PDF / DOCX / HTML inputs. Empty otherwise.
  const uploadMetadata = ref<Record<string, unknown>>({})
  // Remembers the most recently uploaded File so we can re-upload it with a
  // different ``page`` option without asking the user to pick it again.
  const lastFile = ref<File | null>(null)
  const lastOptions = ref<Record<string, unknown> | undefined>(undefined)

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
  // When true, every new layer added by an upload is created with
  // ``optimize: true`` so users get optimized toolpaths by default.
  const autoOptimize = ref(true)

  const selectedProfile = computed(
    () => profiles.value.find((p) => p.name === selectedProfileName.value) ?? null,
  )

  // A machine has a colour magazine when it physically holds more than one
  // pen. Single-pen plotters get a simplified UI that hides per-layer pen
  // assignment, "group by pen" and the magazine strip.
  const isMultiColor = computed<boolean>(
    () => (selectedProfile.value?.pen_slot_count ?? 1) > 1,
  )

  // Per-profile drawing region on the machine workspace, persisted in
  // localStorage. The drawing is the thing the user is plotting; this
  // record stores where on the workspace it sits and at what size. ``null``
  // (unset) means "auto-fit": center the drawing in the workspace minus
  // margins (the legacy behaviour). Keyed by profile name so each machine
  // remembers its last placement independently.
  interface DrawingRegion {
    x_mm: number
    y_mm: number
    width_mm: number
    height_mm: number
  }
  const DRAWINGS_KEY = 'omniplot.drawings.v1'
  function readDrawings(): Record<string, DrawingRegion> {
    try {
      const raw = localStorage.getItem(DRAWINGS_KEY)
      if (!raw) return {}
      const parsed = JSON.parse(raw)
      return typeof parsed === 'object' && parsed !== null ? parsed : {}
    } catch {
      return {}
    }
  }
  const drawingByProfile = ref<Record<string, DrawingRegion>>(readDrawings())
  watch(
    drawingByProfile,
    (value) => {
      try {
        localStorage.setItem(DRAWINGS_KEY, JSON.stringify(value))
      } catch {
        // localStorage may be unavailable (e.g. private mode); failing here
        // is non-fatal — the in-memory placement still works for the session.
      }
    },
    { deep: true },
  )

  // ``null`` means "auto-fit" — the SheetPreview and the backend will scale
  // the drawing to the workspace with the configured margin.
  const currentDrawing = computed<DrawingRegion | null>(() => {
    const profile = selectedProfile.value
    if (!profile) return null
    return drawingByProfile.value[profile.name] ?? null
  })

  function setDrawing(patch: Partial<DrawingRegion>): void {
    const profile = selectedProfile.value
    if (!profile) return
    const ws = profile.workspace
    const wsW = ws.x_max - ws.x_min
    const wsH = ws.y_max - ws.y_min
    const previous =
      drawingByProfile.value[profile.name] ?? {
        x_mm: 0,
        y_mm: 0,
        width_mm: wsW,
        height_mm: wsH,
      }
    drawingByProfile.value = {
      ...drawingByProfile.value,
      [profile.name]: { ...previous, ...patch },
    }
    preflight.value = null
  }

  function resetDrawing(): void {
    const profile = selectedProfile.value
    if (!profile) return
    const next = { ...drawingByProfile.value }
    delete next[profile.name]
    drawingByProfile.value = next
    preflight.value = null
  }

  // Per-layer render-algorithm overrides. Keyed by ``layer_id`` (e.g.
  // ``color-ff0000`` for a bitmap colour layer). Lives in memory only —
  // a fresh upload wipes it. Each entry holds the override algorithm
  // and per-algo options; the backend ``/rerender`` endpoint applies it
  // against the cached segmentation and returns a new SVG.
  interface LayerAlgorithm {
    algorithm: string
    algorithm_options: Record<string, unknown>
  }
  const layerAlgorithms = ref<Record<string, LayerAlgorithm>>({})
  let rerenderController: AbortController | null = null
  let rerenderTimer: ReturnType<typeof setTimeout> | null = null

  async function applyLayerAlgorithm(
    layerId: string,
    algorithm: string,
    algorithmOptions: Record<string, unknown> = {},
  ): Promise<void> {
    layerAlgorithms.value = {
      ...layerAlgorithms.value,
      [layerId]: { algorithm, algorithm_options: algorithmOptions },
    }
    // Debounce the network round-trip so a slider drag doesn't fire a
    // request on every tick.
    if (rerenderTimer) clearTimeout(rerenderTimer)
    rerenderTimer = setTimeout(triggerRerender, 250)
  }

  // Drop the override for a layer and re-render with the original
  // algorithm baked in at upload time. Reassigning the ref (rather than
  // ``delete``) keeps Vue's reactivity in the loop.
  async function clearLayerAlgorithm(layerId: string): Promise<void> {
    if (!(layerId in layerAlgorithms.value)) return
    const next = { ...layerAlgorithms.value }
    delete next[layerId]
    layerAlgorithms.value = next
    if (rerenderTimer) clearTimeout(rerenderTimer)
    rerenderTimer = setTimeout(triggerRerender, 250)
  }

  async function triggerRerender(): Promise<void> {
    const jobId = job.value?.job_id
    if (!jobId || !svg.value) return
    if (rerenderController) rerenderController.abort()
    const controller = new AbortController()
    rerenderController = controller
    try {
      const layersPayload = Object.entries(layerAlgorithms.value).map(
        ([layer_id, spec]) => ({
          layer_id,
          algorithm: spec.algorithm,
          algorithm_options: spec.algorithm_options,
        }),
      )
      const result = await rerenderJob(jobId, layersPayload, controller.signal)
      if (controller.signal.aborted) return
      svg.value = result.svg
      // The toolpath metrics / G-code are now stale — drop them so the
      // operator doesn't ship a G-code that doesn't match the preview.
      metrics.value = null
      gcode.value = null
      preflight.value = null
    } catch (err) {
      if (controller.signal.aborted) return
      const status = (err as { response?: { status?: number } })?.response?.status
      // 404 = cache evicted (LRU / backend restart). Tolerate silently —
      // re-uploading refreshes the cache. 405 = the /rerender route isn't
      // reachable on this deployment (e.g. a static-mount or reverse-proxy
      // ate the POST); show a clear hint instead of the cryptic axios error.
      if (status === 404) {
        // silent
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

  // Pen slots assigned to a layer that are out of range or not installed,
  // mirroring the backend magazine check so generation can be gated.
  const missingPenSlots = computed<number[]>(() => {
    const profile = selectedProfile.value
    if (!profile) return []
    const hasExplicit = (profile.pens?.length ?? 0) > 0
    const installed = new Set(
      (profile.pens ?? []).filter((p) => p.installed).map((p) => p.index),
    )
    const missing = new Set<number>()
    for (const layer of layers.value) {
      const slot = layer.target_pen_slot
      if (slot === null) continue
      if (slot < 0 || slot >= profile.pen_slot_count) missing.add(slot)
      else if (hasExplicit && !installed.has(slot)) missing.add(slot)
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
    layers.value.reduce((sum, layer) => sum + layer.total_length_mm, 0),
  )

  const totalDurationSeconds = computed(() =>
    layers.value.reduce((sum, layer) => sum + layerDurationSeconds(layer), 0),
  )

  function setVisibility(layerId: string, visible: boolean): void {
    visibility.value = { ...visibility.value, [layerId]: visible }
  }

  function isVisible(layerId: string): boolean {
    return visibility.value[layerId] ?? true
  }

  function updateLayer(layerId: string, patch: Partial<LayerInfo>): void {
    layers.value = layers.value.map((layer) =>
      layer.layer_id === layerId ? { ...layer, ...patch } : layer,
    )
    preflight.value = null
  }

  function reorderLayers(ordered: LayerInfo[]): void {
    layers.value = ordered.map((layer, index) => ({ ...layer, draw_order: index }))
    preflight.value = null
  }

  watch([scaleMode, marginMm, selectedProfileName, drawingByProfile], () => {
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

  async function upload(file: File, optionsOverride?: Record<string, unknown>): Promise<void> {
    const preset = presets.value.find((p) => p.name === selectedPresetName.value)
    const options =
      preset?.options || optionsOverride ? { ...preset?.options, ...optionsOverride } : undefined
    loading.value = true
    error.value = null
    errorScope.value = null
    uploadWarnings.value = []
    uploadMetadata.value = {}
    metrics.value = null
    gcode.value = null
    preflight.value = null
    // A new upload invalidates the per-layer algorithm overrides — they
    // reference layer ids from the previous job.
    layerAlgorithms.value = {}
    lastFile.value = file
    lastOptions.value = options
    const toasts = useToastStore()
    try {
      const result = await uploadFile(file, selectedProfileName.value, options)
      job.value = result.job
      svg.value = result.svg
      // Apply ``autoOptimize`` to every freshly-imported layer so the default
      // experience produces optimized toolpaths without an extra click.
      layers.value = result.job.layers.map((layer) =>
        autoOptimize.value ? { ...layer, optimize: true } : layer,
      )
      uploadWarnings.value = result.warnings ?? []
      uploadMetadata.value = result.metadata ?? {}
      visibility.value = Object.fromEntries(
        result.job.layers.map((layer) => [layer.layer_id, true]),
      )
      // Surface upload warnings as toasts; the inline list in SourceSection
      // stays as the durable reference, the toast is the attention grabber.
      for (const warning of uploadWarnings.value.slice(0, 3)) {
        toasts.warning(warning)
      }
      if (uploadWarnings.value.length > 3) {
        toasts.warning(
          i18n.global.t('toast.moreWarnings', { count: uploadWarnings.value.length - 3 }),
        )
      }
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('upload.failed'))
      error.value = message
      errorScope.value = 'upload'
      svg.value = null
      layers.value = []
      toasts.error(message)
    } finally {
      loading.value = false
    }
  }

  function clearJob(): void {
    job.value = null
    svg.value = null
    layers.value = []
    visibility.value = {}
    uploadWarnings.value = []
    uploadMetadata.value = {}
    lastFile.value = null
    lastOptions.value = undefined
    metrics.value = null
    gcode.value = null
    preflight.value = null
    error.value = null
    errorScope.value = null
    // Stale per-layer overrides would point at a job_id that's gone.
    layerAlgorithms.value = {}
  }

  async function changePage(page: number): Promise<void> {
    // Re-upload the same source file with a different ``page`` option;
    // useful for multi-page PDF / DOCX / HTML inputs where the converter
    // returns a ``page_count`` greater than 1.
    if (!lastFile.value) return
    const next = { ...(lastOptions.value ?? {}), page }
    await upload(lastFile.value, next)
  }

  async function optimize(): Promise<void> {
    if (!svg.value) return
    optimizing.value = true
    error.value = null
    errorScope.value = null
    try {
      const result = await optimizeToolpaths(
        svg.value,
        layers.value.map((layer) => ({
          layer_id: layer.layer_id,
          optimize: layer.optimize,
          simplify_tolerance_mm: layer.simplify_tolerance_mm,
        })),
      )
      svg.value = result.svg
      layers.value = result.layers
      metrics.value = result.metrics
      visibility.value = Object.fromEntries(result.layers.map((layer) => [layer.layer_id, true]))
      gcode.value = null
      preflight.value = null
    } catch (err) {
      error.value = errorDetail(err, i18n.global.t('layers.optimizeFailed'))
      errorScope.value = 'optimize'
    } finally {
      optimizing.value = false
    }
  }

  async function runPreflight(): Promise<void> {
    if (!svg.value) return
    preflighting.value = true
    error.value = null
    errorScope.value = null
    try {
      const drawing = currentDrawing.value
      preflight.value = await preflightCheck(
        svg.value,
        selectedProfileName.value,
        layers.value.map((layer) => ({
          layer_id: layer.layer_id,
          target_pen_slot: layer.target_pen_slot,
          drawing_speed_mm_s: layer.drawing_speed_mm_s,
          source_color: layer.source_color,
          color_label: layer.color_label,
          pause_before: layer.pause_before,
        })),
        scaleMode.value,
        marginMm.value,
        // Map the drawing region onto the backend's ``Placement`` payload.
        // The payload's "sheet" fields are interpreted by the generator as
        // the drawing area: same maths, clearer UI naming.
        drawing
          ? {
              sheet_width_mm: drawing.width_mm,
              sheet_height_mm: drawing.height_mm,
              offset_x_mm: drawing.x_mm,
              offset_y_mm: drawing.y_mm,
            }
          : null,
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
    if (!svg.value) return
    generating.value = true
    error.value = null
    errorScope.value = null
    try {
      const drawing = currentDrawing.value
      const result = await generateGcode(
        svg.value,
        selectedProfileName.value,
        layers.value.map((layer) => ({
          layer_id: layer.layer_id,
          target_pen_slot: layer.target_pen_slot,
          drawing_speed_mm_s: layer.drawing_speed_mm_s,
          source_color: layer.source_color,
          color_label: layer.color_label,
          pause_before: layer.pause_before,
        })),
        scaleMode.value,
        marginMm.value,
        drawing
          ? {
              sheet_width_mm: drawing.width_mm,
              sheet_height_mm: drawing.height_mm,
              offset_x_mm: drawing.x_mm,
              offset_y_mm: drawing.y_mm,
            }
          : null,
      )
      gcode.value = result.gcode
    } catch (err) {
      error.value = errorDetail(err, i18n.global.t('layers.generateFailed'))
      errorScope.value = 'generate'
    } finally {
      generating.value = false
    }
  }

  return {
    job,
    svg,
    layers,
    visibility,
    loading,
    error,
    errorScope,
    uploadWarnings,
    uploadMetadata,
    lastFile,
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
    currentDrawing,
    setDrawing,
    resetDrawing,
    layerAlgorithms,
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
    optimize,
    runPreflight,
    generate,
  }
})
