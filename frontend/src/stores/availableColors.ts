// Available-colours inventory store — global app-wide list of inks the
// operator owns, populated via ``GET /available-colors``.
//
// Separate from the library store because the colours are independent of
// any file: they describe the operator's physical drawer, not what's on
// the canvas. The per-layer colour picker in the editor reads this list
// when the active palette source is ``available`` or ``union``.

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  type AvailableColor,
  createAvailableColor,
  deleteAvailableColor,
  listAvailableColors,
  patchAvailableColor,
} from '../api/client'
import { canonicalHex } from '../lib/penWidth'
import { errorDetail } from '../api/error'
import { i18n } from '../i18n'
import { useToastStore } from './toasts'

export const useAvailableColorsStore = defineStore('availableColors', () => {
  const colors = ref<AvailableColor[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  // ``loaded`` flips to true on the first successful refresh so callers
  // can distinguish "empty inventory" from "not fetched yet" — useful
  // when the picker decides whether to show "no colours yet" vs spinner.
  const loaded = ref(false)

  const ordered = computed(() =>
    [...colors.value].sort(
      (a, b) => a.position - b.position || a.created_at.localeCompare(b.created_at),
    ),
  )

  async function refresh(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      colors.value = await listAvailableColors()
      loaded.value = true
    } catch (err) {
      error.value = errorDetail(err, i18n.global.t('availableColors.loadFailed'))
    } finally {
      loading.value = false
    }
  }

  async function add(
    hex: string,
    name: string = '',
    strokeWidthMm?: number,
  ): Promise<AvailableColor | null> {
    error.value = null
    try {
      const created = await createAvailableColor(hex, name, strokeWidthMm)
      // POST is idempotent on hex (backend dedups + may rename) — replace
      // any existing row with the returned shape so the local cache mirrors
      // the server state instead of growing a stale duplicate.
      const idx = colors.value.findIndex((c) => c.color_id === created.color_id)
      if (idx >= 0) colors.value[idx] = created
      else colors.value = [...colors.value, created]
      return created
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('availableColors.createFailed'))
      error.value = message
      useToastStore().error(message)
      return null
    }
  }

  async function rename(
    colorId: string,
    patch: Partial<
      Pick<AvailableColor, 'hex' | 'name' | 'position' | 'stroke_width_mm' | 'odometer_mm'>
    >,
  ): Promise<AvailableColor | null> {
    error.value = null
    try {
      const updated = await patchAvailableColor(colorId, patch)
      const idx = colors.value.findIndex((c) => c.color_id === colorId)
      if (idx >= 0) colors.value[idx] = updated
      return updated
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('availableColors.updateFailed'))
      error.value = message
      useToastStore().error(message)
      return null
    }
  }

  async function resetOdometer(colorId: string): Promise<void> {
    await rename(colorId, { odometer_mm: 0 })
  }

  async function addToOdometer(hex: string, deltaMm: number): Promise<void> {
    if (deltaMm <= 0) return
    const canon = canonicalHex(hex)
    const color = ordered.value.find((c) => c.hex === canon)
    if (!color) return
    await rename(color.color_id, { odometer_mm: color.odometer_mm + deltaMm })
  }

  async function remove(colorId: string): Promise<boolean> {
    error.value = null
    try {
      await deleteAvailableColor(colorId)
      colors.value = colors.value.filter((c) => c.color_id !== colorId)
      return true
    } catch (err) {
      const message = errorDetail(err, i18n.global.t('availableColors.deleteFailed'))
      error.value = message
      useToastStore().error(message)
      return false
    }
  }

  return {
    colors,
    ordered,
    loading,
    loaded,
    error,
    refresh,
    add,
    rename,
    resetOdometer,
    addToOdometer,
    remove,
  }
})
