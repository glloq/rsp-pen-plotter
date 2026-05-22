import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  deleteProfile as apiDeleteProfile,
  saveProfile as apiSaveProfile,
  generateGcode,
  getPresets,
  getProfiles,
  optimizeToolpaths,
  uploadFile,
  type Job,
  type LayerInfo,
  type MachineProfile,
  type Preset,
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

  const profiles = ref<MachineProfile[]>([])
  const selectedProfileName = ref('Custom CoreXY A3')

  const presets = ref<Preset[]>([])
  const selectedPresetName = ref<string>('')

  const optimizing = ref(false)
  const metrics = ref<ToolpathMetrics | null>(null)

  const generating = ref(false)
  const gcode = ref<string | null>(null)

  const scaleMode = ref<'fit' | 'actual'>('fit')
  const marginMm = ref(10)

  const selectedProfile = computed(
    () => profiles.value.find((p) => p.name === selectedProfileName.value) ?? null,
  )

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
  }

  function reorderLayers(ordered: LayerInfo[]): void {
    layers.value = ordered.map((layer, index) => ({ ...layer, draw_order: index }))
  }

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
    metrics.value = null
    gcode.value = null
    try {
      const result = await uploadFile(file, selectedProfileName.value, options)
      job.value = result.job
      svg.value = result.svg
      layers.value = result.job.layers
      visibility.value = Object.fromEntries(
        result.job.layers.map((layer) => [layer.layer_id, true]),
      )
    } catch {
      error.value = 'Upload failed. Check the file type and that the API is running.'
      svg.value = null
      layers.value = []
    } finally {
      loading.value = false
    }
  }

  async function optimize(): Promise<void> {
    if (!svg.value) return
    optimizing.value = true
    error.value = null
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
    } catch {
      error.value = 'Optimization failed.'
    } finally {
      optimizing.value = false
    }
  }

  async function generate(): Promise<void> {
    if (!svg.value) return
    generating.value = true
    error.value = null
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
    } catch {
      error.value = 'G-code generation failed.'
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
    profiles,
    selectedProfileName,
    selectedProfile,
    presets,
    selectedPresetName,
    optimizing,
    metrics,
    generating,
    gcode,
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
    generate,
  }
})
