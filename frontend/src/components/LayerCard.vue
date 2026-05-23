<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { LayerInfo, PausePolicy } from '../api/client'
import { formatLayerLabel } from '../lib/labels'
import { useJobStore } from '../stores/job'

const { t } = useI18n()
const props = defineProps<{ layer: LayerInfo }>()
const store = useJobStore()

const visible = computed({
  get: () => store.isVisible(props.layer.layer_id),
  set: (value: boolean) => store.setVisibility(props.layer.layer_id, value),
})

const label = computed(() => formatLayerLabel(props.layer.layer_id))

const swatchColor = computed(() => label.value.color ?? props.layer.source_color)

const penSlotCount = computed(() => store.selectedProfile?.pen_slot_count ?? 0)

const penSlots = computed(() => {
  const profile = store.selectedProfile
  const pens = profile?.pens ?? []
  return Array.from({ length: penSlotCount.value }, (_, i) => {
    const pen = pens.find((p) => p.index === i)
    return { index: i, name: pen?.name || `${i}`, color: pen?.color ?? '#94a3b8' }
  })
})

const selectedPen = computed(() =>
  props.layer.target_pen_slot === null
    ? null
    : (penSlots.value.find((p) => p.index === props.layer.target_pen_slot) ?? null),
)

function onPenSlot(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  store.updateLayer(props.layer.layer_id, { target_pen_slot: value === '' ? null : Number(value) })
}

function onSpeed(event: Event): void {
  const value = (event.target as HTMLInputElement).value
  store.updateLayer(props.layer.layer_id, {
    drawing_speed_mm_s: value === '' ? null : Number(value),
  })
}

function onSimplify(event: Event): void {
  store.updateLayer(props.layer.layer_id, {
    simplify_tolerance_mm: Number((event.target as HTMLInputElement).value),
  })
}

function onOptimize(event: Event): void {
  store.updateLayer(props.layer.layer_id, {
    optimize: (event.target as HTMLInputElement).checked,
  })
}

function onColorLabel(event: Event): void {
  const raw = (event.target as HTMLInputElement).value.trim()
  store.updateLayer(props.layer.layer_id, { color_label: raw || null })
}

function setPause(policy: PausePolicy): void {
  store.updateLayer(props.layer.layer_id, { pause_before: policy })
}

const pauseChoices: Array<{ value: PausePolicy; icon: string; key: string }> = [
  { value: 'auto', icon: '⏸', key: 'layers.pauseAuto' },
  { value: 'always', icon: '✋', key: 'layers.pauseAlways' },
  { value: 'never', icon: '▶', key: 'layers.pauseNever' },
]

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs.toString().padStart(2, '0')}s`
}

const duration = computed(() => formatDuration(store.layerDurationSeconds(props.layer)))
</script>

<template>
  <div class="rounded border border-slate-700 bg-slate-800 px-3 py-2 space-y-2">
    <div class="flex items-center gap-3">
      <span class="cursor-grab text-slate-500 select-none" :title="t('layers.dragHint')" aria-hidden="true">⠿</span>
      <input v-model="visible" type="checkbox" class="h-4 w-4 accent-emerald-500" />

      <span
        v-if="label.kind === 'image'"
        class="flex h-5 w-5 shrink-0 items-center justify-center rounded border border-slate-600 bg-slate-900 text-[10px]"
        :title="t('layers.kindImage')"
        aria-hidden="true"
      >🖼</span>
      <span
        v-else-if="label.kind === 'text'"
        class="flex h-5 w-5 shrink-0 items-center justify-center rounded border border-slate-600 bg-slate-900 font-serif text-xs text-slate-300"
        :title="t('layers.kindText')"
        aria-hidden="true"
      >Aa</span>
      <span
        v-else
        class="h-5 w-5 rounded border border-slate-600 shrink-0"
        :style="{ backgroundColor: swatchColor }"
      />

      <div class="min-w-0 flex-1">
        <p class="truncate text-sm text-slate-200" :class="label.kind === 'color' ? 'font-mono' : ''">
          {{ label.display }}
        </p>
        <p class="text-xs text-slate-500">
          {{ layer.path_count }} {{ t('layers.paths') }} ·
          {{ layer.total_length_mm.toFixed(1) }} mm · {{ duration }}
        </p>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-2 text-xs">
      <!-- Multi-pen machines: explicit slot assignment. -->
      <label v-if="store.isMultiColor" class="text-slate-400">
        <span class="flex items-center gap-1">
          {{ t('layers.penSlot') }}
          <span
            v-if="selectedPen"
            class="inline-block h-3 w-3 rounded-full border border-slate-600"
            :style="{ backgroundColor: selectedPen.color }"
          />
        </span>
        <select
          :value="layer.target_pen_slot ?? ''"
          class="mt-0.5 w-full rounded bg-slate-900 border border-slate-700 px-1 py-0.5 text-slate-100"
          @change="onPenSlot"
        >
          <option value="">{{ t('layers.none') }}</option>
          <option v-for="pen in penSlots" :key="pen.index" :value="pen.index">
            {{ pen.index }} — {{ pen.name }}
          </option>
        </select>
      </label>
      <!-- Mono-pen machines: colour label used in the pause prompt. -->
      <label v-else class="text-slate-400">
        <span class="flex items-center gap-1">
          {{ t('layers.colorLabel') }}
          <span
            class="inline-block h-3 w-3 rounded-full border border-slate-600"
            :style="{ backgroundColor: swatchColor }"
          />
        </span>
        <input
          type="text"
          :value="layer.color_label ?? ''"
          :placeholder="layer.source_color"
          class="mt-0.5 w-full rounded bg-slate-900 border border-slate-700 px-1 py-0.5 text-slate-100"
          @change="onColorLabel"
        />
      </label>

      <label class="text-slate-400">
        {{ t('layers.speed') }}
        <input
          type="number"
          min="1"
          :value="layer.drawing_speed_mm_s ?? ''"
          :placeholder="t('layers.default')"
          class="mt-0.5 w-full rounded bg-slate-900 border border-slate-700 px-1 py-0.5 text-slate-100"
          @change="onSpeed"
        />
      </label>
      <label class="text-slate-400">
        {{ t('layers.simplify') }}
        <input
          type="number"
          min="0"
          step="0.01"
          :value="layer.simplify_tolerance_mm"
          class="mt-0.5 w-full rounded bg-slate-900 border border-slate-700 px-1 py-0.5 text-slate-100"
          @change="onSimplify"
        />
      </label>
      <label class="flex items-end gap-2 text-slate-400">
        <input
          type="checkbox"
          :checked="layer.optimize"
          class="h-4 w-4 accent-emerald-500"
          @change="onOptimize"
        />
        {{ t('layers.optimize') }}
      </label>
    </div>

    <div class="flex items-center gap-1.5 text-[10px] text-slate-500">
      <span>{{ t('layers.pauseBefore') }}</span>
      <div class="flex overflow-hidden rounded border border-slate-700">
        <button
          v-for="choice in pauseChoices"
          :key="choice.value"
          type="button"
          class="px-2 py-0.5 transition"
          :class="layer.pause_before === choice.value
            ? 'bg-slate-700 text-slate-100'
            : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'"
          :title="t(choice.key)"
          @click="setPause(choice.value)"
        >
          <span aria-hidden="true">{{ choice.icon }}</span>
          <span class="ml-1">{{ t(choice.key) }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
