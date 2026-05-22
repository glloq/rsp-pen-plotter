import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  getProfiles,
  uploadFile,
  type Job,
  type LayerInfo,
  type MachineProfile,
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

  async function upload(file: File, options?: Record<string, unknown>): Promise<void> {
    loading.value = true
    error.value = null
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
    totalLengthMm,
    totalDurationSeconds,
    effectiveSpeed,
    layerDurationSeconds,
    setVisibility,
    isVisible,
    updateLayer,
    reorderLayers,
    loadProfiles,
    upload,
  }
})
