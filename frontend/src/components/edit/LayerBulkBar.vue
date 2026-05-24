<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useJobStore } from '../../stores/job'
import { LayerSelectionKey } from '../../composables/useLayerSelection'
import { layerStyles, type PrintStyle } from '../../data/printRegistry'
import PenSlotPicker from './shared/PenSlotPicker.vue'

// Contextual actions for multi-selected layers. Mounted by
// LayersSection above the layer list, only rendered when at least one
// layer is selected. Three bulk operations:
//
//   - Pen slot       — reassign every selected layer to the picked pen
//   - Render style   — apply a layer-scope preset (algorithm + options)
//                      to every selected layer
//   - Reset overrides — clear ``layer_algorithms[id]`` for every
//                      selected layer so they fall back to the master
//                      style's recipe

const { t } = useI18n()
const store = useJobStore()
const selection = inject(LayerSelectionKey, null)

const visible = computed(() => (selection?.count.value ?? 0) > 0)
const selectedIds = computed(() => [...(selection?.selected.value ?? new Set<string>())])

// Two collapsable popovers: pen picker + style picker. Closed by
// default — bulk operations are deliberate actions and we don't want
// the bar to overflow on first render.
const showPen = ref(false)
const showStyle = ref(false)

const stylesForPicker = computed<PrintStyle[]>(() => layerStyles())

// "Use a single pen for all selected layers" — closes the popover
// after applying so the operator gets visual confirmation the click
// took effect.
function setPenForAll(slot: number): void {
  for (const id of selectedIds.value) {
    store.updateLayer(id, { target_pen_slot: slot })
  }
  showPen.value = false
}

function applyStyleToAll(style: PrintStyle): void {
  for (const id of selectedIds.value) {
    void store.applyLayerAlgorithm(
      id,
      style.defaultAlgorithm,
      { ...style.defaultAlgorithmOptions },
    )
  }
  showStyle.value = false
}

async function resetOverrides(): Promise<void> {
  for (const id of selectedIds.value) {
    // ``applyLayerAlgorithm`` with an empty options dict + the
    // ``direct`` algo is the cheapest way to reset to the default.
    // The store debounces /rerender so all N resets fire one round-trip.
    await store.applyLayerAlgorithm(id, 'direct', {})
  }
}

function clearSelection(): void {
  selection?.clear()
  showPen.value = false
  showStyle.value = false
}
</script>

<template>
  <div
    v-if="visible"
    class="sticky top-12 z-10 flex flex-wrap items-center gap-1 rounded border border-emerald-700 bg-emerald-950/40 px-2 py-1.5 text-[11px]"
  >
    <span class="font-medium text-emerald-200">
      {{ t('layers.bulkSelected', { count: selection?.count.value ?? 0 }) }}
    </span>

    <!-- Pen popover -->
    <div class="relative">
      <button
        type="button"
        class="rounded border border-emerald-700 bg-slate-900 px-2 py-0.5 text-slate-200 hover:border-emerald-500"
        @click="showPen = !showPen; showStyle = false"
      >
        {{ t('layers.bulkPen') }} ▾
      </button>
      <div
        v-if="showPen"
        class="absolute left-0 top-full z-20 mt-1 w-64 rounded border border-slate-700 bg-slate-900 p-2 shadow-lg"
      >
        <PenSlotPicker
          :model-value="-1"
          :show-label="false"
          @update:model-value="setPenForAll"
        />
      </div>
    </div>

    <!-- Style popover -->
    <div class="relative">
      <button
        type="button"
        class="rounded border border-emerald-700 bg-slate-900 px-2 py-0.5 text-slate-200 hover:border-emerald-500"
        @click="showStyle = !showStyle; showPen = false"
      >
        {{ t('layers.bulkStyle') }} ▾
      </button>
      <div
        v-if="showStyle"
        class="absolute left-0 top-full z-20 mt-1 w-72 rounded border border-slate-700 bg-slate-900 p-2 shadow-lg"
      >
        <div class="grid grid-cols-2 gap-1">
          <button
            v-for="style in stylesForPicker"
            :key="style.id"
            type="button"
            class="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-left text-[11px] text-slate-200 hover:border-emerald-500"
            :title="style.descriptionKey ? t(style.descriptionKey) : ''"
            @click="applyStyleToAll(style)"
          >
            {{ t(style.labelKey) }}
          </button>
        </div>
      </div>
    </div>

    <button
      type="button"
      class="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-slate-300 hover:border-rose-500 hover:text-rose-200"
      @click="resetOverrides"
    >
      {{ t('layers.bulkReset') }}
    </button>

    <button
      type="button"
      class="ml-auto rounded px-2 py-0.5 text-slate-400 hover:text-slate-200"
      @click="clearSelection"
    >
      ✕ {{ t('layers.bulkClear') }}
    </button>
  </div>
</template>
