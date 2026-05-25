// Palette-source toggle store.
//
// Holds the operator's choice between three pools for the per-layer
// colour picker:
//
//   - ``pens``      — only the installed pen-slot colours (legacy
//                     "palette follows pens" behaviour)
//   - ``available`` — only the global available-colours inventory
//                     (L1 store, edited in the Plotter drawer)
//   - ``union``     — both, deduplicated by hex
//
// Persisted server-side via ``GET/PUT /settings/palette-source`` so the
// choice survives reloads and is shared across browser tabs.

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { type PaletteSource, getPaletteSource, setPaletteSource } from '../api/client'
import { errorDetail } from '../api/error'
import { i18n } from '../i18n'
import { useToastStore } from './toasts'

export const usePaletteSourceStore = defineStore('paletteSource', () => {
  // Optimistic default: ``pens`` is what the editor used to apply
  // before the source toggle existed, so the UI behaves identically
  // until the GET round-trip lands.
  const source = ref<PaletteSource>('pens')
  const loading = ref(false)
  const loaded = ref(false)

  async function refresh(): Promise<void> {
    loading.value = true
    try {
      source.value = await getPaletteSource()
      loaded.value = true
    } catch (err) {
      // Stale optimistic default is the right fallback: the picker
      // keeps working off ``pens`` while the operator retries.
      useToastStore().error(errorDetail(err, i18n.global.t('paletteSource.loadFailed')))
    } finally {
      loading.value = false
    }
  }

  async function update(next: PaletteSource): Promise<void> {
    const previous = source.value
    source.value = next
    try {
      await setPaletteSource(next)
    } catch (err) {
      // Roll the local state back so the radio reflects what the
      // server actually applies.
      source.value = previous
      useToastStore().error(errorDetail(err, i18n.global.t('paletteSource.updateFailed')))
    }
  }

  return { source, loading, loaded, refresh, update }
})
