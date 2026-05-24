<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  masterStyles,
  resolveMasterStyle,
  LEGACY_MASTER_ID_MAP,
  type PrintStyle,
} from '../../../data/printRegistry'
import StyleThumbnail from '../shared/StyleThumbnail.vue'

// Gallery of master styles (Pencil / Halftone / Stippling / Engraving
// / Contours-topo / Outline / TSP / Spiral). Renders each as a card
// with the style thumbnail + label + one-line description. The grid
// is 2 columns to match the density of the surrounding render tab;
// 3-4 columns would feel sparse for 8 entries.
//
// Selecting a style commits the registry id directly into the draft
// AND mirrors the legacy id (which is what monoModes.ts uses today)
// so older code paths (preview, store-side propagation) keep working
// through the migration.

const props = defineProps<{
  // Active style id — either the registry id (``pencil``,
  // ``halftone-shade``…) or a legacy mono-mode id (``halftone``…).
  modelValue: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const { t } = useI18n()

const styles = computed<PrintStyle[]>(() => masterStyles())

// Match either by registry id or by mapped legacy id so the active
// pill survives both old (``halftone``) and new (``halftone-shade``)
// values living in the draft.
function isActive(style: PrintStyle): boolean {
  if (style.id === props.modelValue) return true
  const mapped = LEGACY_MASTER_ID_MAP[props.modelValue]
  return mapped === style.id
}

function select(style: PrintStyle): void {
  // Emit the registry id; callers that still need the legacy id can
  // map back via ``LEGACY_MASTER_ID_MAP``. The draft setter
  // (``setPrintMode`` / direct write) goes through
  // ``resolveMasterStyle`` so either form is accepted.
  emit('update:modelValue', style.id)
}

// Resolve the active style for the descriptive footer at the bottom
// of the card. Falls back to the default master if the id is unknown.
const activeStyle = computed(() => resolveMasterStyle(props.modelValue))
</script>

<template>
  <div class="space-y-1">
    <p class="text-[10px] uppercase tracking-wider text-slate-400">
      {{ t('render.masterStyle') }}
    </p>
    <div class="grid grid-cols-2 gap-1">
      <button
        v-for="style in styles"
        :key="style.id"
        type="button"
        class="flex items-center gap-2 rounded border px-2 py-1.5 text-left transition"
        :class="isActive(style)
          ? 'border-emerald-600 bg-emerald-950/40 text-emerald-200'
          : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-600'"
        :title="style.descriptionKey ? t(style.descriptionKey) : ''"
        @click="select(style)"
      >
        <StyleThumbnail :algorithm="style.defaultAlgorithm" size="md" />
        <span class="min-w-0 flex-1">
          <span class="block truncate text-[11px] font-medium">
            {{ t(style.labelKey) }}
          </span>
          <span
            v-if="style.descriptionKey"
            class="block truncate text-[9px] text-slate-500"
          >
            {{ t(style.descriptionKey) }}
          </span>
        </span>
      </button>
    </div>
    <p class="text-[10px] text-slate-500">
      {{ activeStyle.descriptionKey ? t(activeStyle.descriptionKey) : '' }}
    </p>
  </div>
</template>
