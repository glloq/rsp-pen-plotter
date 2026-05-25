<script setup lang="ts">
// Read-only header row for LayerCard (L10 #4 extract).
//
// The summary stays visible regardless of the collapse state — it
// hosts the drag handle, visibility toggle, kind icon / colour
// swatch, layer label + path stats, multi-pass badge, and the
// expand/collapse button. All interactions emit back to the parent,
// which forwards to the composable.

import { useI18n } from 'vue-i18n'
import type { LayerInfo } from '../api/client'
import type { formatLayerLabel } from '../lib/labels'

const { t } = useI18n()

type LayerLabel = ReturnType<typeof formatLayerLabel>

defineProps<{
  layer: LayerInfo
  label: LayerLabel
  swatchColor: string
  isMultiPass: boolean
  passCount: number
  duration: string
  collapsed: boolean
  visible: boolean
}>()

const emit = defineEmits<{
  headerClick: [event: MouseEvent]
  'update:collapsed': [value: boolean]
  'update:visible': [value: boolean]
}>()
</script>

<template>
  <div class="flex items-center gap-3" @click="emit('headerClick', $event)">
    <span
      class="cursor-grab text-slate-500 select-none"
      :title="t('layers.dragHint')"
      aria-hidden="true"
      >⠿</span
    >
    <input
      :checked="visible"
      type="checkbox"
      class="h-4 w-4 accent-emerald-500"
      @change="emit('update:visible', ($event.target as HTMLInputElement).checked)"
    />

    <span
      v-if="label.kind === 'image'"
      class="flex h-5 w-5 shrink-0 items-center justify-center rounded border border-slate-600 bg-slate-900 text-[10px]"
      :title="t('layers.kindImage')"
      aria-hidden="true"
      >🖼</span
    >
    <span
      v-else-if="label.kind === 'text'"
      class="flex h-5 w-5 shrink-0 items-center justify-center rounded border border-slate-600 bg-slate-900 font-serif text-xs text-slate-300"
      :title="t('layers.kindText')"
      aria-hidden="true"
      >Aa</span
    >
    <span
      v-else
      class="h-5 w-5 rounded border border-slate-600 shrink-0"
      :style="{ backgroundColor: swatchColor }"
    />

    <div class="min-w-0 flex-1">
      <p
        class="flex items-center gap-1.5 truncate text-sm text-slate-200"
        :class="label.kind === 'color' ? 'font-mono' : ''"
      >
        <span class="truncate">{{ label.display }}</span>
        <span
          v-if="isMultiPass"
          class="shrink-0 rounded-sm border border-emerald-700 bg-emerald-950/60 px-1 py-px text-[9px] font-semibold tracking-wider text-emerald-300"
          :title="t('passes.badgeHint')"
          >×{{ passCount }}</span
        >
      </p>
      <p class="text-xs text-slate-500">
        {{ layer.path_count }} {{ t('layers.paths') }} · {{ layer.total_length_mm.toFixed(1) }} mm ·
        {{ duration }}
      </p>
    </div>
    <button
      type="button"
      class="shrink-0 rounded bg-slate-700 px-1.5 py-0.5 text-[11px] text-slate-200 hover:bg-slate-600"
      :title="collapsed ? t('layers.expand') : t('layers.collapse')"
      :aria-expanded="!collapsed"
      @click="emit('update:collapsed', !collapsed)"
    >
      {{ collapsed ? '▸' : '▾' }}
    </button>
  </div>
</template>
