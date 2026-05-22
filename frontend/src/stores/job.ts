import { defineStore } from 'pinia'
import { ref } from 'vue'
import { uploadFile, type Job, type LayerInfo } from '../api/client'

export const useJobStore = defineStore('job', () => {
  const job = ref<Job | null>(null)
  const svg = ref<string | null>(null)
  const layers = ref<LayerInfo[]>([])
  const visibility = ref<Record<string, boolean>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  function setVisibility(layerId: string, visible: boolean): void {
    visibility.value = { ...visibility.value, [layerId]: visible }
  }

  function isVisible(layerId: string): boolean {
    return visibility.value[layerId] ?? true
  }

  async function upload(
    file: File,
    profileName: string,
    options?: Record<string, unknown>,
  ): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const result = await uploadFile(file, profileName, options)
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
    setVisibility,
    isVisible,
    upload,
  }
})
