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

  const selectedProfile = computed(
    () => profiles.value.find((p) => p.name === selectedProfileName.value) ?? null,
  )

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

  watch([scaleMode, marginMm, selectedProfileName], () => {
    preflight.value = null
  })

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
    lastFile.value = file
    lastOptions.value = options
    const toasts = useToastStore()
    try {
      const result = await uploadFile(file, selectedProfileName.value, options)
      job.value = result.job
      svg.value = result.svg
      layers.value = result.job.layers
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
      preflight.value = await preflightCheck(
        svg.value,
        selectedProfileName.value,
        layers.value.map((layer) => ({
          layer_id: layer.layer_id,
          target_pen_slot: layer.target_pen_slot,
          drawing_speed_mm_s: layer.drawing_speed_mm_s,
        })),
        scaleMode.value,
        marginMm.value,
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
      const result = await generateGcode(
        svg.value,
        selectedProfileName.value,
        layers.value.map((layer) => ({
          layer_id: layer.layer_id,
          target_pen_slot: layer.target_pen_slot,
          drawing_speed_mm_s: layer.drawing_speed_mm_s,
        })),
        scaleMode.value,
        marginMm.value,
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
    scaleMode,
    marginMm,
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
